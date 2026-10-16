// Find instructions that use a float constant, either as an immediate (MOV [x], 0x453b8000)
// or via a memory operand pointing at 4 bytes holding that float.
// Args: <out_file> <float> [<float> ...]
//@category WolfTeam
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;

import java.io.FileWriter;
import java.io.PrintWriter;

public class FindFloat extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (int a = 1; a < args.length; a++) {
                int bits = Float.floatToIntBits(Float.parseFloat(args[a]));
                out.println("## " + args[a] + String.format(" (0x%08x)", bits));
                InstructionIterator it = currentProgram.getListing().getInstructions(true);
                while (it.hasNext()) {
                    Instruction ins = it.next();
                    boolean hit = false;
                    for (int op = 0; op < ins.getNumOperands() && !hit; op++) {
                        for (Object o : ins.getOpObjects(op)) {
                            if (o instanceof Scalar s && (int) s.getUnsignedValue() == bits && s.bitLength() == 32) hit = true;
                        }
                    }
                    if (!hit) {
                        for (Reference r : ins.getReferencesFrom()) {
                            Address t = r.getToAddress();
                            try {
                                if (t.isMemoryAddress() && getInt(t) == bits) hit = true;
                            } catch (Exception e) { /* unreadable */ }
                        }
                    }
                    if (hit) {
                        Function f = getFunctionContaining(ins.getAddress());
                        out.println("  " + ins.getAddress() + "  " + ins + "   in " + (f == null ? "?" : f.getName() + " @ " + f.getEntryPoint()));
                    }
                }
            }
        }
    }
}
