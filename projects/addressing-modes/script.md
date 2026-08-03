---
title: Addressing Modes, Visually
topic: Addressing modes in computer architecture - immediate, direct, register, register indirect, displacement (indexed), and PC-relative addressing
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is what Code2Video animates.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; 8-12 min total = 1100-1700 words. -->

## 1 - One instruction, seven ways to read it
> ANIM: dark screen. Draw one 16-bit instruction as a neat row of sixteen bit cells, colored white on dark blue. Label the leftmost four bits "OPCODE" in yellow and the remaining twelve "OPERAND FIELD" in cyan. Below it fade in a large question mark and the words "WHERE IS THE DATA?" The instruction stays centered the whole scene; later sections will re-light it.

An instruction is just bits. Sixteen of them, say. The first four tell the processor what to do: add, load, branch. The remaining twelve are the interesting part, because they are not the answer to anything yet. They are a question. Where is the data?

Look at the same instruction again and you can answer that question seven different ways, and each answer changes the speed of the program, the size of the program, and even how much memory the chip can talk to at all. These are the addressing modes. And every single program you have ever run is a braid of all of them at once, switching silently on every line.

## 2 - Immediate: the data travels with the instruction
> ANIM: take the 16-bit instruction from before. Highlight the cyan operand field and draw a circle around the bits 0 0 0 0 0 0 1 0 0 1 0 1. Beside the instruction draw a small CPU chip labeled with a lightning bolt. Draw the digits 25 flowing directly from the instruction into the chip through a short glowing arrow, and cross out a faded memory block with a red diagonal so it is clear no memory trip happens. Small caption under: "0 memory accesses".

Start with the fastest, because it is the only mode where the operand does not exist anywhere except inside the instruction itself.

Take those twelve operand bits and declare: these bits ARE the number. Not an address of a number. The number. This is immediate addressing. The instruction says add twenty-five, and the twenty-five is riding along inside the instruction, sitting right there in the fetch-decode-execute pipeline.

The CPU never leaves the chip. No trip to memory, no address bus, nothing. It is the cheapest possible read of a value, and the compiler uses it the moment it knows a constant at compile time.

The catch is the word "compile time". If the value has to change while the program runs, immediate is useless, because the instruction is frozen. And you pay for that speed in instruction width: every constant you bake in eats operand bits, so big constants need multiple instructions just to load. Immediate is fast, but it is static. Which is exactly the problem direct addressing is trying to solve.

## 3 - Direct: the field IS the address
> ANIM: keep the instruction, but now replace the operand field with the hex address 2F4. Draw a horizontal memory strip of twelve boxes, each labeled with an address, and light up box 2F4 in green. Draw a solid arrow from the operand field, down to box 2F4, and a second arrow from box 2F4 back up to the CPU chip. Beneath: "1 memory access". Then morph the strip's addresses to show why twelve bits is a wall: count from 000 to FFF and draw a barrier labeled "only 4K addresses reachable" after FFF, with a small sad value beyond it.

So now let the operand field mean an address. Those twelve bits say: go to location two-F-four, and the number you want is sitting there. This is direct addressing, sometimes called absolute. One memory access, one clean answer, dead simple for the hardware to decode.

But look at what you bought. The instruction field is twelve bits wide, so the largest address it can spell is all ones. On a machine with sixteen-bit instructions, the number of cells the processor can even name is fixed by the width of that field. Twelve bits, four thousand addresses, full stop. A program cannot reach past its own instruction's ability to point.

That is the core tension of every addressing mode. The operand field is the only currency you have. Spend all of it on the address and you can reach the whole world but you have nothing left for flexibility. Spend it on nothing and you are fast but frozen. Every mode that follows is a way to get more reach, or more flexibility, out of those same twelve bits.

## 4 - Register modes: the register file is a tiny fast memory
> ANIM: draw a small register file beside the CPU as a 2-by-4 grid of eight boxes labeled R0 through R7, tinted purple. First show register direct: operand field reads R3, arrow from field to box R3, arrow from R3 into the CPU. Label "register addressing, 0 memory accesses". Then change the operand field to read (R3) with parentheses drawn in red. Show R3 containing the address 2F4, then a long arrow from R3 down to green memory box 2F4, and from 2F4 back to the CPU. Label "register indirect, 1 memory access, address lives in a register".

The register file is a small, extremely fast memory built into the CPU itself. Eight boxes, each with a name: R0 through R7. And here is the trick that costs you nothing: if the operand field names a register instead of an address, the value you want might just be sitting inside that register, and the CPU reaches it in a cycle without touching memory at all. Register addressing. This is the mode behind every single `R1`, `R2` you have ever seen in assembly.

But the interesting one is the next step. Put parentheses around that register name. Now the register does not hold the value, it holds an address, and the value lives wherever that address points. Register indirect addressing.

This is the moment flexibility appears. The instruction does not change. Same twelve bits, still saying "go look at R3". But the contents of R3 can change between executions. One single instruction can now read memory location A on the first run and memory location B on the next, and the processor never needs a new instruction to do it. That one property is what makes loops over arrays possible. The instruction stays frozen in the program, and the pointer does the walking.

## 5 - Displacement and indexed: base plus offset
> ANIM: draw an array of six memory boxes in a horizontal strip, addresses 300, 304, 308, 30C, 310, 314, each holding a value. Draw an instruction whose operand field is the two parts "300" and "+ index". Draw a wide bracket under the strip anchored at 300. Show a red index pointer R5 holding 4, and animate a green highlight sliding along the strip to box 308 as the arrow from the instruction lands on 300+8. Label each box's address as "base + offset". Caption at bottom: "address = base + offset".

Now take register indirect and add a number. The operand field supplies a base, a starting point, and a register supplies an offset. The real address is base plus offset, computed on the fly. Displacement addressing. When the offset comes from an index register, it is called indexed addressing, and the difference matters only in flavour.

Watch why it exists. The base points at the start of a structure, an array or a record. The offset selects the element. And here is the payoff: the base lives in the instruction, fixed; the offset lives in a register, free to change. The same instruction can now read element one on the first pass and element nine on the tenth pass. That is a for loop compiled into hardware. No branch, no relocating pointers, no rewriting anything.

The arithmetic cost is real but tiny: one add inside the address unit before the memory request. And the reach is enormous, because the offset register can hold a number far wider than the twelve-bit field, so base plus offset can reach memory the field could never describe alone. Same field width, whole new universe of addresses.

## 6 - PC-relative: the distance, not the place
> ANIM: draw a row of five instructions side by side, labeled addresses 100, 104, 108, 10C, 110. The middle instruction (108) is a branch. Draw a dashed arrow from the branch instruction bending down and right to instruction 110, and label the gap "+2". Then shift the whole row of instructions right by three boxes, showing the dashed arrow and its "+2" label staying glued to the instructions, still landing on the right target. Caption: "address = PC + offset - the code can move".

There is one more mode worth its own look, and it powers every if, every loop, every function call. The operand field holds neither an address nor a value, but a distance. A signed offset from the current instruction, added to the program counter. PC-relative addressing.

The branch instruction says: jump forward two instructions. Not jump to address one-ten. Two forward. And the difference is not pedantry, because now the whole program can be picked up and moved to a different place in memory and every branch still lands exactly where it should, because every branch is just measuring its own distance. Relocation happens for free. A program loaded at address one hundred and the same program loaded at address one million behave identically, because no branch anywhere contains an absolute address. The instruction and its target move as one.

That is why this is the mode compilers reach for on every control-flow instruction, and it is why a security flaw that lets an attacker rewrite the distance inside a branch can quietly redirect a whole program. The price of portability is that a small corruption becomes a big hijack.

## 7 - The trade-off, in one table
> ANIM: build a four-column table row by row. Columns: Mode, What the field holds, Memory accesses, Flexibility. Rows light up in order: Immediate - the value itself - 0 - frozen. Direct - an address - 1 - fixed target. Register - a register name - 0 - fast, few operands. Register indirect - a register holding an address - 1 - target can change. Displacement - base + offset - 1-2 - arrays and records. PC-relative - distance from PC - 1 - code can move. End with all six rows glowing and a single line under the table: "Every program braids all six."

So here is the whole map. Immediate spends the field on the value itself: zero memory access, frozen at compile time. Direct spends it on an address: one access, but only as far as the field can point. Register modes spend it on a name: fast, and when you add parentheses, the target can change while the instruction stays put. Displacement adds an offset so one instruction can walk a whole array. And PC-relative spends the field on a distance so the entire program can be relocated without rewriting a single branch.

Six answers to the same question, where is the data. And a real program is never one of them. It is all of them, weaving, because each mode is a different point on the trade between speed and reach and flexibility, and a good compiler spends that twelve-bit budget where it buys the most.

Which leaves the natural next question: the CPU has to figure out, on every single instruction, which of these six interpretations to use. That is the decode step, the moment the instruction's bits decide how the rest of the pipeline behaves. That is exactly what we will animate next.
