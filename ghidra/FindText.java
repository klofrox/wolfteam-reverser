// List functions containing instructions whose text contains a given substring
// (e.g. a global address "0x346387c4"). Args: <out_file> <substring> [<substring> ...]
//@category WolfTeam
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashMap;
import java.util.Map;

public class FindText extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (int i = 1; i < args.length; i++) {
                String needle = args[i].toLowerCase();
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
