package agent;

import java.lang.instrument.Instrumentation;
import java.net.URL;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;

public final class RenderAgent {
    public static void agentmain(String directory, Instrumentation instrumentation) throws Exception {
        Path root = Paths.get(directory).toRealPath();
        String prefix=Boolean.getBoolean("gtnh.preview.background")?"worker-":"";
        try {
            Class<?> minecraft = null;
            for (Class<?> candidate : instrumentation.getAllLoadedClasses()) {
                if (candidate.getName().equals("net.minecraft.client.Minecraft")) minecraft = candidate;
            }
            if (minecraft == null) throw new IllegalStateException("Minecraft has not initialized yet");
            ClassLoader loader = minecraft.getClassLoader();
            Thread.currentThread().setContextClassLoader(loader);
            String rendererJar = new String(Files.readAllBytes(root.resolve("renderer-file.txt")), StandardCharsets.UTF_8).trim();
            loader.getClass().getMethod("addURL", URL.class).invoke(loader, root.resolve(rendererJar).toUri().toURL());
            Path active = root.resolve(prefix+"active-class.txt");
            if (Files.exists(active)) {
                String previous = new String(Files.readAllBytes(active), StandardCharsets.UTF_8).trim();
                try { Class.forName(previous, true, loader).getMethod("stop").invoke(null); }
                catch (ClassNotFoundException ignored) { /* A new game process has no previous module. */ }
            }
            String implementation = new String(Files.readAllBytes(root.resolve("renderer-class.txt")), StandardCharsets.UTF_8).trim();
            Class.forName(implementation, true, loader).getMethod("install", String.class).invoke(null, root.toString());
            Files.write(active, implementation.getBytes(StandardCharsets.UTF_8));
            Files.deleteIfExists(root.resolve(prefix+"attach-error.txt"));
        } catch (Throwable error) {
            Files.write(root.resolve(prefix+"attach-error.txt"), stack(error).getBytes(StandardCharsets.UTF_8));
            throw new RuntimeException(error);
        }
    }

    private static String stack(Throwable error) {
        java.io.StringWriter text = new java.io.StringWriter();
        error.printStackTrace(new java.io.PrintWriter(text));
        return text.toString();
    }
}
