package agent;

import com.sun.tools.attach.VirtualMachine;
import java.nio.file.Paths;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;

public final class Attach {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("PID and renderer directory required");
        String root = Paths.get(args[1]).toRealPath().toString();
        VirtualMachine vm = VirtualMachine.attach(args[0]);
        String jar = new String(Files.readAllBytes(Paths.get(root,"agent-file.txt")), StandardCharsets.UTF_8).trim();
        try { vm.loadAgent(root + "/" + jar, root); }
        finally { vm.detach(); }
        System.out.println("Native renderer attached");
    }
}
