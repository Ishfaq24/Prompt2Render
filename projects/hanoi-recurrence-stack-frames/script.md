---
title: Solving Tower of Hanoi via Recurrence and Stack Frames
topic: Tower of Hanoi - recursive decomposition, frame-by-frame move execution for N=3, recursive call tree, recurrence relation T(n)=2T(n-1)+1, O(2^n) time complexity, inductive optimality proof
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~11 min total = ~1540 words
     across 7 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - The Rules and the 3-Disk Puzzle
> ANIM: Animate 3 disks of sizes 1, 2, and 3 stacked on Peg A, attempting an illegal placement of disk 3 onto disk 1 on Peg B to highlight the constraint rules.

How do we solve a classic algorithmic puzzle where local constraints force an exponentially deep cascade of choices? The Tower of Hanoi begins with three vertical pegs labeled A, B, and C. On Peg A, we place n disks of strictly increasing diameters, stacked from the largest at the bottom to the smallest at the top. Our goal is to transfer the entire stack from Peg A to Peg C while obeying two strict invariants. First, we may only move one disk at a time, taking the topmost disk from any peg and placing it onto another peg. Second, a larger disk can never sit on top of a smaller disk. Placing disk 3 directly onto disk 1 violates this second constraint immediately, rendering the move invalid. To build a systematic algorithm rather than relying on manual trial and error, we need a general method that guarantees we never violate these rules while moving any arbitrary number of disks.

## 2 - The Recursive Subproblem Strategy
> ANIM: Visualise top disks 1 and 2 grouped into a single highlighted subproblem transferred from Peg A to Peg B, freeing disk 3 to move directly to Peg C.

Instead of attacking the full problem all at once, consider the structural necessity of moving the largest disk. To move disk 3 from Peg A to Peg C, Peg C must be empty or hold an even larger disk, and Peg A must have disk 3 entirely exposed. This means the upper subproblem of disks 1 and 2 must first be completely removed from Peg A and positioned on the auxiliary peg, Peg B. This reveals the core recursive decomposition of the Tower of Hanoi. Solving a problem of size n reduces to three sequential sub-tasks. First, recursively transfer the top n minus 1 disks from the source peg to the auxiliary peg. Second, execute a single direct move of disk n from the source peg to the target peg. Third, recursively transfer the n minus 1 disks from the auxiliary peg onto the target peg. By reducing the size of the unplaced stack by one at each step, the problem recursively unwinds until it hits the base case where n equals zero, which requires no moves at all.

## 3 - Tracing the 7 Moves for 3 Disks
> ANIM: Trace each of the 7 exact disk moves step-by-step across Pegs A, B, and C with a step counter running from 1 to 7.

Let us trace this exact sequence for three disks, moving the stack from Peg A to Peg C using Peg B as auxiliary storage. Step 1 moves disk 1 from Peg A to Peg C. Step 2 moves disk 2 from Peg A to Peg B. Step 3 moves disk 1 from Peg C to Peg B, successfully completing the first recursive subproblem of moving two disks out of the way. Step 4 performs the critical base operation for disk 3, moving disk 3 directly from Peg A to Peg C. Now we must move the two-disk subproblem from Peg B to Peg C. Step 5 moves disk 1 from Peg B to Peg A. Step 6 moves disk 2 from Peg B to Peg C. Finally, Step 7 moves disk 1 from Peg A to Peg C. In exactly seven discrete steps, the entire stack of three disks has been reconstructed on Peg C without ever placing a larger disk on a smaller disk.

## 4 - Mapping Execution to the Recursive Call Tree
> ANIM: Show Python code for hanoi(3, A, C, B) side-by-side with an expanding recursive call tree highlighting the active stack frame at each step.

We can represent this execution directly in code with a recursive function call, passing the number of disks alongside the source, target, and auxiliary pegs. Calling hanoi with parameters 3, A, C, and B pushes the root frame onto the call stack. Because n is greater than zero, this frame pauses its execution and spawns a child stack frame to move two disks from A to B using C. That child frame in turn pauses to spawn a frame moving one disk from A to C using B. As execution flows downward, base case calls with n equal to zero return immediately, popping off the stack and allowing the parent frame to execute its single disk movement. The call stack directly reflects the structure of a binary call tree. Each internal node represents a recursive invocation that splits into two child calls separated by a single central move operation, precisely controlling which peg serves as source, target, or auxiliary at every level of depth.

## 5 - Deriving Complexity from the Recurrence Relation
> ANIM: Unroll the recurrence equation T(n) = 2T(n-1) + 1 step-by-step to arrive at T(n) = 2^n - 1, displaying an exponential growth curve.

To quantify the computational work required by this algorithm, we express its running time as a recurrence relation. Let T of n denote the number of disk moves required to solve a problem of size n. Our recursive strategy performs two subproblems of size n minus 1 plus one direct move, giving the relation T of n equals 2 times T of n minus 1 plus 1, with the base case T of 0 equal to 0. Unrolling this equation step-by-step reveals a geometric series. T of n equals 2 times the quantity 2 T of n minus 2 plus 1, plus 1, which simplifies to 4 T of n minus 2 plus 2 plus 1. Repeated substitution yields the summation of powers of 2 from 2 to the power 0 up to 2 to the power n minus 1. Summing this finite geometric series yields exactly 2 to the power n minus 1 moves. As n grows, the running time grows exponentially, placing the algorithm in the complexity class Big O of 2 to the power n.

## 6 - Proving Minimum Move Optimality
> ANIM: Display an induction proof alongside an animation demonstrating that disk N cannot move to its target peg in fewer than 2^n - 1 total operations.

We have shown our algorithm takes 2 to the power n minus 1 moves, but can any algorithm do better? We can prove that 2 to the power n minus 1 is the strict lower bound using mathematical induction. For the base case where n equals 1, 2 to the power 1 minus 1 equals 1 move, which is clearly minimal. Now assume that moving a stack of k disks requires at least 2 to the power k minus 1 moves. To move a stack of k plus 1 disks, disk k plus 1 must eventually move from the source peg to the target peg. Before disk k plus 1 can move, all k smaller disks resting above it must be cleared off the source peg, requiring at least 2 to the power k minus 1 moves by the inductive hypothesis. Moving disk k plus 1 itself requires 1 move. Finally, placing those k disks back on top of disk k plus 1 requires another 2 to the power k minus 1 moves. Adding these together gives 2 times 2 to the power k minus 1, plus 1, which equals 2 to the power k plus 1 minus 1. Thus, by induction, no valid sequence of moves can ever solve the puzzle in fewer than 2 to the power n minus 1 operations.

## 7 - Recap and the Iterative Alternative
> ANIM: Recap the recursive divide-and-conquer strategy before contrasting the call tree with a preview of an iterative, bit-manipulation solver.

The recursive divide-and-conquer strategy offers an elegant, optimal solution by decomposing the Tower of Hanoi into identical subproblems tracked naturally through nested stack frames. However, maintaining deep recursive call trees incurs function call overhead and stack memory proportional to the height of the tree. Remarkably, because the exact sequence of disk movements follows a rigid periodic pattern, we can eliminate recursion and stack allocation entirely. By examining the binary representation of the move counter or using bitwise operations, an iterative algorithm can determine precisely which disk to move and where to place it at every step. How can simple binary counting generate the exact same optimal sequence of moves without ever invoking a recursive call?

