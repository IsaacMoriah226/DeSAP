// Prints, for each string given as a script argument, the functions that reference it and their decompiled code.
// Headless: analyzeHeadless <proj dir> <proj> -process <program> -noanalysis -readOnly -scriptPath <this dir>
//           -postScript FindStringUsers.java <out file> <max lines per function> <string>...
// @category DeSAP

import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;

public class FindStringUsers extends GhidraScript {
	@Override
	protected void run() throws Exception {
		String[] args = getScriptArgs();
		try (PrintWriter out = new PrintWriter(args[0], "UTF-8")) {
			int maxLines = Integer.parseInt(args[1]);
			DecompInterface decomp = new DecompInterface();
			decomp.openProgram(currentProgram);
			Memory memory = currentProgram.getMemory();
			for (int a = 2; a < args.length; a++) {
				String wanted = args[a];
				byte[] needle = (wanted + "\0").getBytes("UTF-8");
				out.println("##### " + wanted);
				Address at = memory.findBytes(currentProgram.getMinAddress(), needle, null, true, monitor);
				int hits = 0;
				while (at != null && hits < 8) {
					hits++;
					out.println("string at " + at);
					Set<Function> users = new LinkedHashSet<>();
					for (Reference ref : getReferencesTo(at)) {
						Function f = getFunctionContaining(ref.getFromAddress());
						out.println("  ref from " + ref.getFromAddress() + (f != null ? " in " + f.getName() + " @ " + f.getEntryPoint() : ""));
						if (f != null) users.add(f);
					}
					for (Function f : users) {
						DecompileResults r = decomp.decompileFunction(f, 60, monitor);
						out.println("---- " + f.getName() + " @ " + f.getEntryPoint());
						if (r != null && r.getDecompiledFunction() != null) {
							String[] lines = r.getDecompiledFunction().getC().split("\n");
							for (int i = 0; i < Math.min(lines.length, maxLines); i++) out.println(lines[i]);
						}
					}
					at = memory.findBytes(at.add(1), needle, null, true, monitor);
				}
			}
		}
	}
}
