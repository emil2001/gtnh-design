package gtnh.preview;

import com.google.gson.*;
import cpw.mods.fml.common.FMLCommonHandler;
import cpw.mods.fml.common.eventhandler.SubscribeEvent;
import cpw.mods.fml.common.gameevent.TickEvent;
import org.lwjgl.opengl.*;
import org.apache.logging.log4j.*;
import org.apache.logging.log4j.core.*;
import org.apache.logging.log4j.core.appender.AbstractAppender;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.lang.reflect.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** A local, file-driven render service; it never places blocks or changes player position. */
public final class NativeRenderer {
    private static final Gson JSON = new GsonBuilder().setPrettyPrinting().create();
    private static final boolean BACKGROUND=Boolean.getBoolean("gtnh.preview.background");
    private static NativeRenderer instance;
    private final Path root;
    private long nextPoll;
    private boolean rendering;
    private final List<String> renderErrors = new ArrayList<String>();

    private NativeRenderer(Path root) { this.root = root; }

    public static synchronized void stop() {
        if (instance != null) FMLCommonHandler.instance().bus().unregister(instance);
    }

    public static synchronized void install(String directory) throws Exception {
        if (instance != null) return;
        instance = new NativeRenderer(Paths.get(directory).toRealPath());
        AbstractAppender appender = new AbstractAppender("NativeSchematicRenderer", null, null) {
            public void append(LogEvent event) {
                if (instance.rendering && event.getLoggerName().toLowerCase(Locale.ROOT).contains("schematica")) {
                    instance.renderErrors.add(event.getLevel() + ": " + event.getMessage().getFormattedMessage()
                        + (event.getThrown() == null ? "" : " — " + event.getThrown()));
                }
            }
        };
        appender.start();
        ((LoggerContext) LogManager.getContext(false)).getConfiguration().getLoggerConfig("").addAppender(appender, Level.WARN, null);
        FMLCommonHandler.instance().bus().register(instance);
        Map<String,Object> state = new LinkedHashMap<String,Object>();
        state.put("status", "attached");
        state.put("backend", "Minecraft + Schematica + installed mod renderers");
        state.put("pid", java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0]);
        state.put("implementation", NativeRenderer.class.getName());
        state.put("background_worker",BACKGROUND);
        write(instance.root.resolve(BACKGROUND?"worker-service.json":"service.json"), state);
    }

    @SubscribeEvent
    public void onRender(TickEvent.RenderTickEvent event) {
        if (!BACKGROUND && event.phase==TickEvent.Phase.END) poll();
    }

    @SubscribeEvent
    public void onClientTick(TickEvent.ClientTickEvent event) {
        // Background workers skip normal frames; client ticks still own the GL context.
        if (BACKGROUND && event.phase==TickEvent.Phase.END) poll();
    }

    private void poll() {
        if (rendering || System.currentTimeMillis() < nextPoll) return;
        nextPoll = System.currentTimeMillis() + 300;
        if (BACKGROUND && Files.isRegularFile(root.resolve("worker-stop.json"))) {
            try {
                Path stop=root.resolve("worker-stop.json");
                JsonObject command=new JsonParser().parse(new String(Files.readAllBytes(stop),StandardCharsets.UTF_8)).getAsJsonObject();
                String pid=java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0];
                Files.delete(stop);
                if (pid.equals(command.get("pid").getAsString())) {
                    Object mc=invoke(type("net.minecraft.client.Minecraft"),null,"func_71410_x");
                    invoke(mc.getClass(),mc,"func_71400_g");
                }
            } catch (Exception error) {
                try { write(root.resolve("worker-stop-error.json"),error.toString()); } catch (Exception ignored) { }
            }
            return;
        }
        Path request = root.resolve(BACKGROUND?"worker-request.json":"request.json");
        if (!Files.isRegularFile(request)) return;
        Map<String,Object> result = new LinkedHashMap<String,Object>();
        Path output = null;
        try {
            JsonObject job = new JsonParser().parse(new String(Files.readAllBytes(request), StandardCharsets.UTF_8)).getAsJsonObject();
            String id = job.get("id").getAsString();
            if (!id.matches("[a-zA-Z0-9_-]{1,80}")) throw new IllegalArgumentException("Invalid job id");
            output = root.getParent().resolve("renders").resolve(id);
            Files.createDirectories(output);
            Class<?> mcType = type("net.minecraft.client.Minecraft");
            Object mc = invoke(mcType,null,"func_71410_x");
            JsonObject bindings=new JsonParser().parse(new String(Files.readAllBytes(root.resolve("bindings.json")),StandardCharsets.UTF_8)).getAsJsonObject();
            Path expectedGame=Paths.get(bindings.get(BACKGROUND?"worker_game":"interactive_game").getAsString()).toRealPath();
            String previewWorld=bindings.get("preview_world").getAsString();
            if (!((java.io.File)get(mc,"field_71412_D")).toPath().toRealPath().equals(expectedGame)) throw new IllegalStateException("Wrong Minecraft instance");
            if (BACKGROUND) {
                long window=((Number)invoke(type("org.lwjglx.opengl.Display"),null,"getWindow")).longValue();
                Class<?> video=type("org.lwjgl.sdl.SDLVideo");
                long flags=((Number)invoke(video,null,"SDL_GetWindowFlags",window)).longValue();
                boolean hidden=(flags&video.getField("SDL_WINDOW_HIDDEN").getLong(null))!=0;
                boolean mouse=(Boolean)invoke(type("org.lwjgl.sdl.SDLMouse"),null,"SDL_GetWindowRelativeMouseMode",window);
                if (!hidden || mouse) throw new IllegalStateException("Worker window/input isolation failed");
                result.put("background_worker",true);result.put("window_hidden",hidden);result.put("mouse_relative_mode",mouse);
                result.put("worker_pid",java.lang.management.ManagementFactory.getRuntimeMXBean().getName().split("@")[0]);
                set(mc,"field_71454_w",true);
            }
            if (get(mc,"field_71441_e") == null) {
                result.put("status","loading_preview_world");
                write(output.resolve("result.json"),result);
                if (invoke(mcType,mc,"func_71401_C") == null) {
                    if (!Files.isRegularFile(expectedGame.resolve("saves").resolve(previewWorld).resolve("level.dat"))) throw new IllegalStateException("Preview world is missing");
                    invoke(mcType,mc,"func_71371_a",previewWorld,"GTNH Render Studio",null);
                }
                return;
            }
            Files.move(request, output.resolve("request.json"), StandardCopyOption.REPLACE_EXISTING);
            result.put("id", id);
            result.put("status", "rendering");
            write(output.resolve("result.json"), result);
            rendering = true;
            renderErrors.clear();
            render(job, output, result);
            result.put("renderer_messages", new ArrayList<String>(renderErrors));
            if (!renderErrors.isEmpty()) throw new IllegalStateException("Schematica reported render/import errors");
            result.put("status", "complete");
        } catch (Throwable error) {
            try {
                if (Files.exists(request)) Files.move(request, output == null ? root.resolve("failed-request.json") : output.resolve("request.json"), StandardCopyOption.REPLACE_EXISTING);
            } catch (Exception ignored) { /* Preserve the original error. */ }
            result.put("status", "failed");
            java.io.StringWriter text = new java.io.StringWriter();
            error.printStackTrace(new java.io.PrintWriter(text));
            result.put("error", text.toString());
            result.put("renderer_messages", new ArrayList<String>(renderErrors));
        } finally {
            rendering = false;
            try { write(output == null ? root.resolve("last-error.json") : output.resolve("result.json"), result); }
            catch (Exception ignored) { System.err.println("Native renderer could not write its result"); }
        }
    }

    private void render(JsonObject job, Path output, Map<String,Object> result) throws Exception {
        Path source = Paths.get(job.get("schematic").getAsString()).toRealPath();
        Path workspace = root.getParent().getParent().toRealPath();
        if (!source.startsWith(workspace) || !Files.isRegularFile(source)) throw new IllegalArgumentException("Schematic must be in this workspace");
        int width = job.has("width") ? job.get("width").getAsInt() : 1600;
        int height = job.has("height") ? job.get("height").getAsInt() : 1000;
        if (width < 128 || width > 4096 || height < 128 || height > 4096) throw new IllegalArgumentException("Invalid image dimensions");
        Class<?> mcType = type("net.minecraft.client.Minecraft");
        Object mc = invoke(mcType, null, "func_71410_x");
        if (get(mc, "field_71441_e") == null) throw new IllegalStateException("A local preview world must be open");
        Object nbt = invoke(type("com.github.lunatrius.schematica.world.schematic.SchematicUtil"), null, "readTagCompoundFromFile", source.toFile());
        Object mapping = invoke(nbt.getClass(), nbt, "func_74775_l", "SchematicaMapping");
        Object registry = invoke(type("cpw.mods.fml.common.registry.GameData"), null, "getBlockRegistry");
        List<String> missing = new ArrayList<String>();
        for (Object name : (Set<?>)invoke(mapping.getClass(), mapping, "func_150296_c")) {
            if (!(Boolean)invoke(registry.getClass(), registry, "contains", name)) missing.add(name.toString());
        }
        if (!missing.isEmpty()) throw new IllegalArgumentException("Blocks missing from this client: " + missing);
        Object tileTags = invoke(nbt.getClass(), nbt, "func_150295_c", "TileEntities", 10);
        int expectedTiles = (Integer)invoke(tileTags.getClass(), tileTags, "func_74745_c");
        Object data = invoke(type("com.github.lunatrius.schematica.world.schematic.SchematicFormat"), null, "readFromFile", source.toFile());
        if (data == null) throw new IllegalArgumentException("Schematica could not read the file");
        int importedTiles=((List<?>)invoke(data.getClass(),data,"getTileEntities")).size();
        if (importedTiles!=expectedTiles) throw new IllegalStateException("TileEntity count mismatch: expected "+expectedTiles+", imported "+importedTiles);
        int sx = (Integer) invoke(data.getClass(), data, "getWidth");
        int sy = (Integer) invoke(data.getClass(), data, "getHeight");
        int sz = (Integer) invoke(data.getClass(), data, "getLength");
        if (sx < 1 || sy < 1 || sz < 1 || (long)sx*sy*sz > 16000000L) throw new IllegalArgumentException("Preview volume exceeds 16 million cells");
        Object extended = invoke(nbt.getClass(),nbt,"func_74775_l","GTNHPreviewMetadata");
        result.put("context_metadata_above_alpha_range",((Set<?>)invoke(extended.getClass(),extended,"func_150296_c")).size());
        Object multipartTags=invoke(nbt.getClass(),nbt,"func_150295_c","GTNHPreviewMultipart",10);
        int multipartCount=(Integer)invoke(multipartTags.getClass(),multipartTags,"func_74745_c");
        for (int i=0; i<multipartCount; i++) {
            Object tag=invoke(multipartTags.getClass(),multipartTags,"func_150305_b",i);
            Object partsTag=invoke(tag.getClass(),tag,"func_150295_c","parts",10);
            Object parts=type("scala.collection.mutable.ListBuffer").getConstructor().newInstance();
            int count=(Integer)invoke(partsTag.getClass(),partsTag,"func_74745_c");
            for (int j=0; j<count; j++) {
                Object partTag=invoke(partsTag.getClass(),partsTag,"func_150305_b",j);
                String id=(String)invoke(partTag.getClass(),partTag,"func_74779_i","id");
                Object part=id.startsWith("mcr_")
                    ? invoke(type("codechicken.multipart.MultiPartRegistry"),null,"loadPart",id,partTag)
                    : invoke(type("codechicken.multipart.MultiPartRegistry"),null,"createPart",id,true);
                if (part==null) throw new IllegalStateException("Unknown multipart: "+id);
                if (!id.startsWith("mcr_")) invoke(part.getClass(),part,"load",partTag);
                invoke(parts.getClass(),parts,"$plus$eq",part);
            }
            Object generator=type("codechicken.multipart.MultipartGenerator$").getField("MODULE$").get(null);
            Object tile=invoke(generator.getClass(),generator,"generateCompositeTile",null,parts,true);
            invoke(tile.getClass(),tile,"func_145839_a",tag);
            invoke(tile.getClass(),tile,"loadParts",parts);
            int x=(Integer)invoke(tag.getClass(),tag,"func_74762_e","x"), y=(Integer)invoke(tag.getClass(),tag,"func_74762_e","y"), z=(Integer)invoke(tag.getClass(),tag,"func_74762_e","z");
            if (x<0 || x>=sx || y<0 || y>=sy || z<0 || z>=sz) throw new IllegalArgumentException("Multipart outside preview");
            if (((List<?>)invoke(tile.getClass(),tile,"jPartList")).size()!=count) throw new IllegalStateException("Multipart pieces were lost");
            invoke(data.getClass(),data,"setTileEntity",x,y,z,tile);
        }
        result.put("multipart_blocks",multipartCount);
        Object schematic = type("com.github.lunatrius.schematica.client.world.SchematicWorld")
            .getConstructor(type("com.github.lunatrius.schematica.api.ISchematic")).newInstance(data);
        Object position = get(schematic, "position");
        set(position, "x", 0); set(position, "y", 1024); set(position, "z", 0);
        Class<?> globalType = type("com.github.lunatrius.schematica.client.renderer.RendererSchematicGlobal");
        Object global = globalType.getField("INSTANCE").get(null);
        Class<?> proxy = type("com.github.lunatrius.schematica.proxy.ClientProxy");
        Object oldSchematic = proxy.getField("schematic").get(null);
        Object playerPosition = proxy.getField("playerPosition").get(null);
        double px = ((Number)get(playerPosition,"x")).doubleValue(), py = ((Number)get(playerPosition,"y")).doubleValue(), pz = ((Number)get(playerPosition,"z")).doubleValue();
        Class<?> config = type("com.github.lunatrius.schematica.handler.ConfigurationHandler");
        Map<String,Object> saved = new LinkedHashMap<String,Object>();
        for (String key : new String[]{"enableAlpha","alpha","highlight","drawQuads","drawLines"}) saved.put(key,config.getField(key).get(null));
        int oldFramebuffer = GL11.glGetInteger(GL30.GL_FRAMEBUFFER_BINDING);
        int oldActiveTexture = GL11.glGetInteger(GL13.GL_ACTIVE_TEXTURE);
        Class<?> forgeHooks = type("net.minecraftforge.client.ForgeHooksClient");
        int oldRenderPass = (Integer)invoke(type("net.minecraftforge.client.MinecraftForgeClient"),null,"getRenderPass");
        Field worldRenderPass=forgeHooks.getDeclaredField("worldRenderPass"); worldRenderPass.setAccessible(true);
        int oldWorldRenderPass=worldRenderPass.getInt(null);
        int framebuffer = 0, texture = 0, depth = 0;
        boolean pushed = false;
        try {
            config.getField("enableAlpha").set(null,false); config.getField("alpha").set(null,1.0f);
            config.getField("highlight").set(null,false); config.getField("drawQuads").set(null,false); config.getField("drawLines").set(null,false);
            GL11.glPushAttrib(GL11.GL_ALL_ATTRIB_BITS);
            GL11.glMatrixMode(GL11.GL_PROJECTION); GL11.glPushMatrix();
            GL11.glMatrixMode(GL11.GL_MODELVIEW); GL11.glPushMatrix();
            pushed = true;
            framebuffer = GL30.glGenFramebuffers(); GL30.glBindFramebuffer(GL30.GL_FRAMEBUFFER, framebuffer);
            texture = GL11.glGenTextures(); GL11.glBindTexture(GL11.GL_TEXTURE_2D,texture);
            GL11.glTexImage2D(GL11.GL_TEXTURE_2D,0,GL11.GL_RGBA8,width,height,0,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,(ByteBuffer)null);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MIN_FILTER,GL11.GL_LINEAR);
            GL11.glTexParameteri(GL11.GL_TEXTURE_2D,GL11.GL_TEXTURE_MAG_FILTER,GL11.GL_LINEAR);
            GL30.glFramebufferTexture2D(GL30.GL_FRAMEBUFFER,GL30.GL_COLOR_ATTACHMENT0,GL11.GL_TEXTURE_2D,texture,0);
            depth = GL30.glGenRenderbuffers(); GL30.glBindRenderbuffer(GL30.GL_RENDERBUFFER,depth);
            GL30.glRenderbufferStorage(GL30.GL_RENDERBUFFER,GL14.GL_DEPTH_COMPONENT24,width,height);
            GL30.glFramebufferRenderbuffer(GL30.GL_FRAMEBUFFER,GL30.GL_DEPTH_ATTACHMENT,GL30.GL_RENDERBUFFER,depth);
            if (GL30.glCheckFramebufferStatus(GL30.GL_FRAMEBUFFER) != GL30.GL_FRAMEBUFFER_COMPLETE) throw new IllegalStateException("Incomplete framebuffer");
            invoke(globalType,global,"createRendererSchematicChunks",schematic);
            List<?> chunks = (List<?>)get(global,"sortedRendererSchematicChunk");
            for (Object chunk : chunks) {
                // Schematica's third pass is only needed for highlights and breaks ArchitectureCraft.
                Field listField=chunk.getClass().getDeclaredField("glList"); listField.setAccessible(true);
                Field highlightField=chunk.getClass().getDeclaredField("glListHighlight"); highlightField.setAccessible(true);
                int list=listField.getInt(chunk), highlight=highlightField.getInt(chunk);
                Object box=invoke(chunk.getClass(),chunk,"getBoundingBox");
                int x0=((Number)get(box,"field_72340_a")).intValue(), y0=((Number)get(box,"field_72338_b")).intValue(), z0=((Number)get(box,"field_72339_c")).intValue();
                int x1=Math.min(sx,((Number)get(box,"field_72336_d")).intValue());
                int y1=Math.min(sy,((Number)get(box,"field_72337_e")).intValue());
                int z1=Math.min(sz,((Number)get(box,"field_72334_f")).intValue());
                for (int pass=0;pass<2;pass++) {
                    invoke(forgeHooks,null,"setRenderPass",pass);
                    worldRenderPass.setInt(null,pass);
                    GL11.glNewList(list+pass,GL11.GL_COMPILE);
                    try { invoke(chunk.getClass(),chunk,"renderBlocks",pass,x0,y0,z0,x1,y1,z1); }
                    finally { GL11.glEndList(); }
                    GL11.glNewList(highlight+pass,GL11.GL_COMPILE); GL11.glEndList();
                }
                set(chunk,"isInFrustrum",true);
            }
            List<String> images = new ArrayList<String>();
            float[][] views = {{45,30},{135,30},{225,30},{315,30},{0,90},{45,-30}};
            String[] names = {"iso-ne","iso-se","iso-sw","iso-nw","top","underside"};
            for (int view = 0; view < views.length; view++) {
                GL30.glBindFramebuffer(GL30.GL_FRAMEBUFFER,framebuffer);
                GL11.glViewport(0,0,width,height);
                GL11.glClearColor(.10f,.12f,.15f,1f); GL11.glClear(GL11.GL_COLOR_BUFFER_BIT|GL11.GL_DEPTH_BUFFER_BIT);
                GL11.glEnable(GL11.GL_DEPTH_TEST); GL11.glDepthMask(true); GL11.glDepthFunc(GL11.GL_LEQUAL);
                GL11.glDisable(GL11.GL_FOG); GL11.glDisable(GL11.GL_LIGHTING); GL11.glDisable(GL11.GL_SCISSOR_TEST);
                GL11.glEnable(GL11.GL_CULL_FACE); GL11.glCullFace(GL11.GL_BACK);
                GL11.glEnable(GL11.GL_BLEND); GL11.glBlendFunc(GL11.GL_SRC_ALPHA,GL11.GL_ONE_MINUS_SRC_ALPHA);
                GL11.glEnable(GL11.GL_ALPHA_TEST); GL11.glAlphaFunc(GL11.GL_GREATER,.1f);
                GL13.glActiveTexture(GL13.GL_TEXTURE1); GL11.glDisable(GL11.GL_TEXTURE_2D);
                GL13.glActiveTexture(GL13.GL_TEXTURE0); GL11.glEnable(GL11.GL_TEXTURE_2D); GL11.glColor4f(1,1,1,1);
                camera(sx,sy,sz,width,height,views[view][0],views[view][1]);
                for (int pass=0; pass<2; pass++) for (Object chunk : chunks) {
                    invoke(forgeHooks,null,"setRenderPass",pass);
                    worldRenderPass.setInt(null,pass);
                    Object center = get(chunk,"centerPosition");
                    set(playerPosition,"x",((Number)get(center,"x")).doubleValue());
                    set(playerPosition,"y",1024+((Number)get(center,"y")).doubleValue());
                    set(playerPosition,"z",((Number)get(center,"z")).doubleValue());
                    invoke(chunk.getClass(),chunk,"render",pass);
                }
                savePixels(output.resolve(names[view]+".png"),width,height);
                images.add(names[view]+".png");
            }
            result.put("images",images); result.put("size",Arrays.asList(width,height));
            result.put("schematic_dimensions",Arrays.asList(sx,sy,sz));
            result.put("tile_entities",((List<?>)invoke(schematic.getClass(),schematic,"getTileEntities")).size());
            result.put("entities",((List<?>)invoke(data.getClass(),data,"getEntities")).size());
            int glError=GL11.glGetError();
            result.put("gl_error",glError);
            if (glError!=0) throw new IllegalStateException("OpenGL error "+glError);
        } finally {
            invoke(forgeHooks,null,"setRenderPass",oldRenderPass);
            worldRenderPass.setInt(null,oldWorldRenderPass);
            invoke(globalType,global,"destroyRendererSchematicChunks");
            if (oldSchematic != null) invoke(globalType,global,"createRendererSchematicChunks",oldSchematic);
            for (Map.Entry<String,Object> e : saved.entrySet()) config.getField(e.getKey()).set(null,e.getValue());
            set(playerPosition,"x",px); set(playerPosition,"y",py); set(playerPosition,"z",pz);
            GL30.glBindFramebuffer(GL30.GL_FRAMEBUFFER,oldFramebuffer);
            if (depth!=0) GL30.glDeleteRenderbuffers(depth);
            if (texture!=0) GL11.glDeleteTextures(texture);
            if (framebuffer!=0) GL30.glDeleteFramebuffers(framebuffer);
            if (pushed) {
                GL11.glMatrixMode(GL11.GL_MODELVIEW); GL11.glPopMatrix();
                GL11.glMatrixMode(GL11.GL_PROJECTION); GL11.glPopMatrix();
                GL11.glPopAttrib(); GL11.glMatrixMode(GL11.GL_MODELVIEW);
            }
            GL13.glActiveTexture(oldActiveTexture);
        }
    }

    private static void camera(int sx,int sy,int sz,int width,int height,float yaw,float pitch) {
        double a=Math.toRadians(yaw), b=Math.toRadians(pitch), mx=0,my=0;
        for (int x : new int[]{-1,1}) for (int y : new int[]{-1,1}) for (int z : new int[]{-1,1}) {
            double vx=x*sx/2.0,vy=y*sy/2.0,vz=z*sz/2.0;
            mx=Math.max(mx,Math.abs(Math.cos(a)*vx+Math.sin(a)*vz));
            my=Math.max(my,Math.abs(Math.cos(b)*vy-Math.sin(b)*(-Math.sin(a)*vx+Math.cos(a)*vz)));
        }
        double halfY=Math.max(my,mx*height/width)*1.12,halfX=halfY*width/height;
        double radius=Math.sqrt((double)sx*sx+(double)sy*sy+(double)sz*sz);
        GL11.glMatrixMode(GL11.GL_PROJECTION); GL11.glLoadIdentity();
        GL11.glOrtho(-halfX,halfX,-halfY,halfY,-radius*3,radius*3);
        GL11.glMatrixMode(GL11.GL_MODELVIEW); GL11.glLoadIdentity();
        GL11.glRotatef(pitch,1,0,0); GL11.glRotatef(yaw,0,1,0); GL11.glTranslated(-sx/2.0,-sy/2.0,-sz/2.0);
    }

    private static void savePixels(Path file,int width,int height) throws Exception {
        ByteBuffer pixels=ByteBuffer.allocateDirect(width*height*4);
        GL11.glPixelStorei(GL11.GL_PACK_ALIGNMENT,1);
        GL11.glReadPixels(0,0,width,height,GL11.GL_RGBA,GL11.GL_UNSIGNED_BYTE,pixels);
        BufferedImage image=new BufferedImage(width,height,BufferedImage.TYPE_INT_ARGB);
        for (int y=0;y<height;y++) for (int x=0;x<width;x++) {
            int i=(y*width+x)*4;
            int rgba=((pixels.get(i+3)&255)<<24)|((pixels.get(i)&255)<<16)|((pixels.get(i+1)&255)<<8)|(pixels.get(i+2)&255);
            image.setRGB(x,height-1-y,rgba);
        }
        if (!ImageIO.write(image,"PNG",file.toFile())) throw new IllegalStateException("PNG writer unavailable");
    }

    private static Class<?> type(String name) throws Exception { return Class.forName(name,true,NativeRenderer.class.getClassLoader()); }
    private static Object get(Object target,String name) throws Exception { return target.getClass().getField(name).get(target); }
    private static void set(Object target,String name,Object value) throws Exception { target.getClass().getField(name).set(target,value); }
    private static Object invoke(Class<?> klass,Object target,String name,Object... args) throws Exception {
        outer: for (Method method : klass.getMethods()) {
            if (!method.getName().equals(name) || method.getParameterTypes().length!=args.length) continue;
            Class<?>[] types=method.getParameterTypes();
            for (int i=0;i<args.length;i++) if (args[i]!=null && !types[i].isPrimitive() && !types[i].isInstance(args[i])) continue outer;
            return method.invoke(target,args);
        }
        throw new NoSuchMethodException(klass.getName()+"."+name);
    }
    private static void write(Path file,Object value) throws Exception {
        Path tmp=file.resolveSibling(file.getFileName()+".tmp");
        Files.write(tmp,JSON.toJson(value).getBytes(StandardCharsets.UTF_8));
        Files.move(tmp,file,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
    }
}
