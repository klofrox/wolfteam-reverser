// For every CALL to the XOR-protected value getter/setter (default 0x340016b0 / 0x340016d0 in cshell),
// print the function, call address and the instruction that loaded ECX just before it (e.g. "LEA ECX,[EDI + 0x60]").
// Args: <out_file> [<hexaddr> ...]   (callee addresses; default 340016b0 340016d0)
//@category WolfTeam
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;

public class XorReads extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String[] targets = args.length > 1 ? java.util.Arrays.copyOfRange(args, 1, args.length) : new String[] {"340016b0", "340016d0"};
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (String t : targets) {
                Address callee = toAddr(Long.parseLong(t, 16));
                for (Reference r : getReferencesTo(callee)) {
                    Address from = r.getFromAddress();
                    Function f = getFunctionContaining(from);
                    Instruction ins = getInstructionAt(from);
                    String ecx = "?";
                    Instruction p = ins == null ? null : ins.getPrevious();
                    for (int i = 0; i < 6 && p != null; i++, p = p.getPrevious()) {
                        String s = p.toString();
                        if (s.startsWith("LEA ECX,") || s.startsWith("MOV ECX,") || s.startsWith("ADD ECX,")) { ecx = s; break; }
                        if (s.startsWith("CALL")) break;
                    }
                    out.println(t + "\t" + (f == null ? "?" : f.getName()) + "\t" + from + "\t" + ecx);
                }
            }
        }
    }
}
