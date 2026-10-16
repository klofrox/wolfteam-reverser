// List and decompile the virtual methods of classes whose vftable symbol matches.
// Args: <out_file> <decompile:0|1> <ClassName> [<ClassName> ...]
//@category WolfTeam
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;

import java.io.FileWriter;
import java.io.PrintWriter;

public class ClassMethods extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        boolean decomp = args[1].equals("1");
        DecompInterface ifc = new DecompInterface();
        ifc.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (int a = 2; a < args.length; a++) {
                String cls = args[a];
                SymbolIterator it = currentProgram.getSymbolTable().getSymbols("vftable");
                while (it.hasNext()) {
                    Symbol s = it.next();
                    String ns = s.getParentNamespace().getName(true);
                    if (!ns.equals(cls) && !ns.endsWith("::" + cls)) continue;
                    out.println("## " + ns + " vftable @ " + s.getAddress());
                    Address p = s.getAddress();
                    for (int i = 0; i < 200; i++) {
                        Address target = toAddr(getInt(p.add(i * 4L)) & 0xffffffffL);
                        Function f = getFunctionAt(target);
                        if (f == null) break;
                        out.println(String.format("  [%3d] +0x%03x  %s @ %s", i, i * 4, f.getName(), f.getEntryPoint()));
                        if (decomp) {
                            DecompileResults r = ifc.decompileFunction(f, 60, monitor);
                            if (r.decompileCompleted()) out.println(r.getDecompiledFunction().getC());
                        }
                    }
                }
            }
        }
    }
}
