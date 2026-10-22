package agent;

import java.lang.instrument.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.ProtectionDomain;
import java.util.*;
import jdk.internal.org.objectweb.asm.*;

/** Worker-only policy: SDL creates hidden windows; never reveal or capture input. */
public final class BackgroundAgent {
    public static void premain(String directory, Instrumentation instrumentation) throws Exception {
        final Path root=Paths.get(directory).toRealPath();
        System.setProperty("gtnh.preview.background","true");
        instrumentation.addTransformer(new ClassFileTransformer() {
            public byte[] transform(ClassLoader loader,String name,Class<?> redefined,
                                    ProtectionDomain domain,byte[] bytes) {
                final String method;
                final String descriptor;
                if ("org/lwjgl/sdl/SDLVideo".equals(name)) {
                    method="SDL_ShowWindow";descriptor="(J)Z";
                } else if ("org/lwjgl/sdl/SDLMouse".equals(name)) {
                    method="SDL_SetWindowRelativeMouseMode";descriptor="(JZ)Z";
                } else return null;
                try {
                    final List<String> patched=new ArrayList<String>();
                    ClassReader reader=new ClassReader(bytes);
                    ClassWriter writer=new ClassWriter(reader,ClassWriter.COMPUTE_MAXS);
                    reader.accept(new ClassVisitor(Opcodes.ASM8,writer) {
                        public MethodVisitor visitMethod(int access,String n,String d,String sig,String[] errors) {
                            MethodVisitor out=super.visitMethod(access,n,d,sig,errors);
                            if ((n.equals(method)&&d.equals(descriptor))
                                    || (n.equals("SDL_RaiseWindow")&&d.equals("(J)Z"))) {
                                out.visitCode();out.visitInsn(Opcodes.ICONST_1);out.visitInsn(Opcodes.IRETURN);
                                out.visitMaxs(1,3);out.visitEnd();patched.add(n);
                                return null;
                            }
                            return out;
                        }
                    },0);
                    if (!patched.contains(method)) throw new IllegalStateException("Unsupported SDL method: "+method);
                    String json="{\"pid\":"+ProcessHandle.current().pid()+",\"class\":\""+name+"\",\"patched\":\""+String.join(",",patched)+"\"}";
                    Files.write(root.resolve(name.endsWith("SDLVideo")?"worker-video-agent.json":"worker-mouse-agent.json"),json.getBytes(StandardCharsets.UTF_8));
                    return writer.toByteArray();
                } catch (Throwable failure) {
                    try { Files.write(root.resolve("worker-agent-error.txt"),failure.toString().getBytes(StandardCharsets.UTF_8)); }
                    catch (Exception ignored) { }
                    // Instrumentation otherwise ignores transformer errors and reveals the window.
                    Runtime.getRuntime().halt(71);
                    return null;
                }
            }
        });
    }
}
