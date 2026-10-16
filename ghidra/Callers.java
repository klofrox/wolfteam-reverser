// Decompile the callers of functions at the given addresses (one level up).
// Args: <out_file> <hexaddr> [<hexaddr> ...]
//@category WolfTeam
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class Callers extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            Set<Function> callers = new LinkedHashSet<>();
            for (int i = 1; i < args.length; i++) {
                Address a = toAddr(Long.parseLong(args[i], 16));
                for (Reference r : getReferencesTo(a)) {
                    Function f = getFunctionContaining(r.getFromAddress());
                    out.println("// " + args[i] + " called from " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName()));
                    if (f != null) callers.add(f);
                }
            }
            for (Function f : callers) {
                DecompileResults res = ifc.decompileFunction(f, 120, monitor);
                out.println("\n// ===== " + f.getName() + " @ " + f.getEntryPoint());
                out.println(res.getDecompiledFunction() == null ? "// (failed)" : res.getDecompiledFunction().getC());
            }
        }
    }
}
