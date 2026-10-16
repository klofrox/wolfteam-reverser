// Decompile every function that references a defined string containing one of the
// given substrings, plus its direct callees (depth configurable).
// Args: <out_file> <depth> <substring> [<substring> ...]
// Also accepts "fn:<hexaddr>" to decompile a function at an address.
//@category WolfTeam
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class DecompStrings extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        int depth = Integer.parseInt(args[1]);
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        Set<Function> roots = new LinkedHashSet<>();
        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            for (int i = 2; i < args.length; i++) {
                String pat = args[i];
                if (pat.startsWith("fn:")) {
                    Address a = toAddr(Long.parseLong(pat.substring(3), 16));
                    Function f = getFunctionContaining(a);
                    if (f != null) roots.add(f);
                    continue;
                }
                DataIterator it = currentProgram.getListing().getDefinedData(true);
                while (it.hasNext()) {
                    Data d = it.next();
                    if (!d.hasStringValue()) continue;
                    Object v = d.getValue();
                    if (v == null || !v.toString().toLowerCase().contains(pat.toLowerCase())) continue;
                    out.println("// string " + d.getAddress() + " \"" + v + "\"");
                    for (Reference r : getReferencesTo(d.getAddress())) {
                        Function f = getFunctionContaining(r.getFromAddress());
                        out.println("//   ref from " + r.getFromAddress() + " in " + (f == null ? "?" : f.getName() + " @ " + f.getEntryPoint()));
                        if (f != null) roots.add(f);
                    }
                }
            }
            Set<Function> all = new LinkedHashSet<>(roots);
            Set<Function> frontier = new LinkedHashSet<>(roots);
            for (int d = 0; d < depth; d++) {
                Set<Function> next = new LinkedHashSet<>();
                for (Function f : frontier) {
                    for (Function c : f.getCalledFunctions(monitor)) {
                        if (!c.isExternal() && !c.isThunk() && all.add(c)) next.add(c);
                    }
                }
                frontier = next;
            }
            for (Function f : all) {
                DecompileResults res = ifc.decompileFunction(f, 60, monitor);
                out.println("\n// ===== " + f.getName() + " @ " + f.getEntryPoint() + (roots.contains(f) ? " (root)" : ""));
                out.println(res.decompileCompleted() ? res.getDecompiledFunction().getC() : "// decompile failed: " + res.getErrorMessage());
            }
        }
        println("wrote " + outPath);
    }
}
