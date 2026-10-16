// List functions containing instructions that use a given struct displacement,
// e.g. "+ 0x45c]". Args: <out_file> <hexdisp> [<hexdisp> ...]
//@category WolfTeam
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

public class FindOffset extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (int i = 1; i < args.length; i++) {
                String needle = "+ 0x" + args[i].toLowerCase() + "]";
                Map<Function, StringBuilder> hits = new LinkedHashMap<>();
                InstructionIterator it = currentProgram.getListing().getInstructions(true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    String s = ins.toString().toLowerCase();
                    if (!s.contains(needle)) continue;
                    Function f = getFunctionContaining(ins.getAddress());
                    if (f == null) continue;
                    hits.computeIfAbsent(f, k -> new StringBuilder()).append("    ").append(ins.getAddress()).append("  ").append(ins).append("\n");
                }
                out.println("## " + needle + "  (" + hits.size() + " functions)");
                for (var e : hits.entrySet()) {
                    out.println("  " + e.getKey().getName() + " @ " + e.getKey().getEntryPoint());
                    out.print(e.getValue());
                }
            }
        }
    }
}
