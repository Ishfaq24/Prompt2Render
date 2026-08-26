---
title: Fetch, Decode, Execute - Animated
topic: The fetch-decode-execute cycle - how a CPU turns stored program bits into action, walked through with one tiny concrete program
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; 8-12 min total = 1100-1700 words. -->

## 1 - A program is just numbers, sitting still
> ANIM: dark screen. Fade in a single row of instruction bits sitting quietly in a memory strip, nothing else moving. Below it, fade in the words "WHAT MAKES THIS RUN?" Hold on stillness for a beat before the next section wakes the diagram up.

Before anything happens, a program is nothing but numbers sitting in memory. Rows of bits. Looked at cold, they don't look different from a photo, or a spreadsheet, or silence. Nothing about the bits themselves says "do this now."

So what turns a still row of numbers into a running program, into a video playing, a page loading, a game responding to your thumb?

One thing, happening over and over, billions of times a second: the processor fetches one instruction, figures out what it means, does it, and moves to the next. Fetch, decode, execute. That loop is the entire secret. Every click, every frame, every keystroke your computer has ever handled is that same three-step loop, running so fast it looks like something else entirely.

It is also, deliberately, a dumb loop. The CPU doesn't understand your program the way you do — it has no idea it's running a browser, or a game, or this very video. It only ever knows one thing at a time: the next single instruction, and what to do with it. Complexity is not something the CPU has. Complexity is something that emerges from this loop running fast enough, often enough, that it stops looking like a loop at all. Today we slow it back down until you can see every single step.

## 2 - Four parts, before anything moves
> ANIM: introduce four labeled boxes and a memory strip, each lighting up in turn as it's named: a small box "PC" (program counter), a small box "IR" (instruction register), a tiny register file grid labeled R0-R3, a box labeled "ALU", and a horizontal memory strip of numbered cells below all of it. End with all five lit at once, quietly, before the loop begins.

Before we run the loop, meet the five things it moves between. The program counter, PC, is a single number: the address of the next instruction to fetch. Nothing more. The instruction register, IR, is a holding cell — whatever instruction was just fetched sits there while it's being worked on. The register file is a handful of small, fast storage slots inside the chip itself, here just four of them, R0 through R3. The ALU, the arithmetic logic unit, is the part that actually adds, subtracts, and compares. And memory is the long strip of numbered cells underneath everything, holding both the program's instructions and its data, side by side, indistinguishable except by how they get used.

Five parts. One loop connecting them, run once per instruction.

## 3 - Fetch: read the next instruction, then move on
> ANIM: show PC holding the address 100, an arrow from PC down to memory cell 100, the bits at that cell traveling up into the IR box, then PC itself changing from 100 to 101 with a small "+1" label on the arrow.

Fetch is the simplest step, and it only does two things. First, the CPU takes whatever address is sitting in the program counter and reads the instruction stored at that address in memory, copying it into the instruction register. Second — and this is the part people forget — the program counter is immediately updated to point at the next instruction, before this one has even been decoded. The CPU always fetches one step ahead of where it currently is. That's the entire fetch stage: one read, one increment. Nothing about the instruction's meaning is examined yet. It is just bits, in transit.

Notice what fetch does not need to know. It doesn't need to know if the instruction is a load or a branch or something that halts the machine entirely. The address in the program counter is just a number, and reading memory at a number is the same operation no matter what's stored there. That's what makes fetch fast, and it's why it's drawn first, every time: it's the one step in this whole loop that never has to think.

## 4 - Decode: the bits declare their own meaning
> ANIM: take the bits now sitting in IR and split the row into two labeled fields, a shorter "OPCODE" field on the left in yellow and a longer "OPERAND" field on the right in cyan. Draw a small branching arrow from the opcode field into a short table of three rows — LOAD, ADD, STORE — with the matching opcode value beside each, one row highlighting to show which one this instruction selected.

Now the CPU looks at what it just fetched. An instruction is not one lump of meaning — it's built from fields, and the first field, the opcode, says which operation this is. Load a value from memory. Add two registers. Store a value back to memory. Branch somewhere else entirely. The remaining bits, the operand field, are decoded according to whatever the opcode demands — sometimes a register name, sometimes a memory address, sometimes both. Decode doesn't change anything yet. It's pure interpretation: turning a number into a decision about what the execute stage is about to do.

## 5 - Execute: the one step that actually changes anything
> ANIM: show three small branching paths fanning out from the decoded opcode, each landing on a different piece of hardware lighting up: one path lights the arrow from memory into a register, one path lights the ALU with two register inputs merging into a sum, one path lights an arrow from a register out into memory. Only one path is lit per instruction.

Execute is where state actually changes — the only step in the whole cycle that does. And what "execute" means depends entirely on what decode just found. If the opcode was load, the CPU reads memory using the decoded address and drops the value into a register. If it was add, the ALU takes two register values, adds them, and writes the sum back into a register. If it was store, a register's value is written out to memory. Fetch just moves bits. Decode just interprets them. Execute is the moment the machine's actual state — its registers, its memory — is different than it was a moment ago.

This is also why execute is the step where things can go visibly wrong. Add two numbers that overflow a register, and the wrong answer is written down right here. Load from an address that was never meant to be read, and this is the step that actually touches memory it shouldn't. Fetch and decode are safe by comparison — they only look. Execute is the step that acts, and acting is where consequences live.

Then the whole loop repeats, at the address the program counter is already pointing to.

## 6 - One tiny program, three full cycles
> ANIM: build a persistent trace panel: PC value top-left, IR contents beside it, the four-register file R0-R3 along the top, and an eight-cell memory strip along the bottom with cell 4 holding 7 and cell 5 initially empty, R2 already holding 5. Step through three complete fetch-decode-execute cycles for a three-instruction program shown as a small code listing on the left with the active line highlighted: (1) LOAD R1, [4] — cell 4's value 7 travels into R1; (2) ADD R1, R1, R2 — the ALU lights up combining R1's 7 and R2's 5 into 12, written back to R1; (3) STORE R1, [5] — R1's 12 travels out to memory cell 5, which lights up green holding 12. PC advances by one after every fetch, and the highlighted code line tracks it exactly.

Let's run the whole loop on a real, tiny program. Three instructions. Memory cell four already holds the number seven. Register R2 already holds five. Watch the program counter the entire time — it's the only thing that tells you where you are in this story.

Cycle one: PC says 100. Fetch reads the instruction at 100 into IR, and PC quietly becomes 101. Decode splits it open: opcode says load, operand says register R1, address 4. Execute reads memory cell four — the seven — and drops it into R1. R1 now holds seven.

Cycle two: PC says 101. Fetch reads the next instruction, PC becomes 102. Decode: opcode says add, operands say R1 and R2. Execute sends R1's seven and R2's five into the ALU. Seven plus five is twelve. That twelve is written back into R1. R1 now holds twelve.

Cycle three: PC says 102. Fetch reads the last instruction, PC becomes 103. Decode: opcode says store, operands say R1, address 5. Execute takes R1's twelve and writes it out to memory cell five. Cell five, which started empty, now holds twelve.

Three instructions, three trips around the same loop, and a number that started as two separate values in memory and a register ended up added together and saved. Nothing about this required anything clever. It required the loop to run three times, correctly, in order.

## 7 - The loop that never stops
> ANIM: recap card, three lines lighting up in sequence: "FETCH - read the instruction, move PC on", "DECODE - the bits declare their own meaning", "EXECUTE - the only step that changes state". Beneath the three lines, zoom out from the single trace panel to a blurred wall of thousands of identical loops running in parallel, then fade to a single question: "WHAT IF THE NEXT FETCH DIDN'T WAIT?"

That's the whole machine, really. Fetch reads an instruction and moves the program counter on. Decode reveals what the bits mean without changing anything. Execute is the one step where the machine's actual state moves. Three steps, one loop, run again and again, billions of times a second, and every program you have ever run is just this cycle in a very long trench coat.

But watch cycle two again. Fetch happened, then decode waited for it, then execute waited for that. The next instruction's fetch didn't start until this one was completely finished. That's correct, and it's also slow — the CPU spends most of each cycle with three of its five parts sitting idle. What if the next instruction's fetch could start while this one was still executing? That overlap has a name, and it's the natural next thing this loop makes possible.
