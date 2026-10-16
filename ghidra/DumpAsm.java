// Dump the disassembly of functions at the given addresses.
// Args: <out_file> <hexaddr> [<hexaddr> ...]
//@category WolfTeam
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpAsm extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (int i = 1; i < args.length; i++) {
                Function f = getFunctionContaining(toAddr(Long.parseLong(args[i], 16)));
                if (f == null) {
                    out.println("// no function at " + args[i]);
                    continue;
                }
                out.println("\n// ===== " + f.getName() + " @ " + f.getEntryPoint());
                InstructionIterator it = currentProgram.getListing().getInstructions(f.getBody(), true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    String extra = "";
                    for (var ref : ins.getReferencesFrom()) {
                        Function t = getFunctionAt(ref.getToAddress());
                        if (t != null) extra += "  ; -> " + t.getName();
                    }
                    out.println(ins.getAddress() + "  " + ins + extra);
                }
            }
        }
    }
}
