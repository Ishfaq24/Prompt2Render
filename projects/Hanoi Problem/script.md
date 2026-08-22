---
title: Recursive Mastery: Unraveling the Tower of Hanoi
topic: Tower of Hanoi, recursive problem-solving, base cases, exponential time complexity, recurrence relations, O(2^n) growth
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; ~13 min total = ~1820 words
     across 8 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build. -->

## 1 - The 64 Golden Disks of Brahma
> ANIM: Display three wooden pegs labeled A, B, and C with a stack of 4 numbered disks on peg A, showing the illegal move restriction: never place a larger disk on a smaller one.

Imagine a legendary temple where monks must move a towering stack of sixty-four golden disks from one sacred post to another. Legend says that when the final move is complete, the universe itself will dissolve. To prevent premature cosmic collapse, the monks must follow two strict rules. Every move shifts only a single disk from one peg to another, and at no point in the process can a larger disk ever rest on top of a smaller one. Starting with four disks on the first peg, the challenge is to find an efficient strategy that respects these constraints across all three pegs.

## 2 - Solving the 1-Disk and 2-Disk Cases
> ANIM: Animate the step-by-step manual moves for 1 disk (A->C) and 2 disks (A->B, A->C, B->C), establishing the pattern of intermediate states.

To understand the larger puzzle, we must start with the simplest possible version. Moving a single disk requires just one direct step from the starting peg to the target peg. When we increase the stack to two disks, the process requires a temporary detour. First, we move the top smaller disk to the middle auxiliary peg, freeing the bottom disk so it can slide directly to the final peg. Finally, we move the small disk from the middle peg onto the bottom disk, completing the two-disk transfer in three total moves and revealing the foundational rhythm of the puzzle.

## 3 - The 3-Disk Manual Trace
> ANIM: Trace the 7 exact moves for 3 disks on pegs A, B, and C, highlighting how the top 2 disks must shift to the spare peg before moving the bottom disk.

That rhythmic pattern becomes even clearer when we scale up to three disks. Moving three disks from peg A to peg C requires seven precise steps. First, the top disk moves to peg C, and the second disk moves to peg B, allowing the small disk to join it on peg B. This clears the largest disk on peg A, which now slides directly to peg C. To finish, the two smaller disks must migrate from peg B over to peg C, using peg A as their temporary station. Every single one of those seven moves serves a specific purpose in clearing the path for the largest disk.

## 4 - Discovering the Recursive Subproblem
> ANIM: Show a visual split of the 3-disk stack into two logical blocks: the top 2 disks moving to peg B, and the 3rd disk moving to peg C.

Looking closely at that three-disk sequence reveals a powerful structural insight. Solving the puzzle is never about moving disks one by one in an ad-hoc fashion. Instead, the entire operation breaks down into three distinct phases. First, we must treat the top two disks as a single smaller unit and shift them entirely out of the way onto the spare peg. That frees the third and largest disk, allowing it to glide straight to its final destination. Once that bottom disk is secure, those top two disks execute the exact same routine to land right on top of it.

## 5 - Formalizing the Recurrence Relation
> ANIM: Display the mathematical equation T(n) = 2T(n-1) + 1 alongside the base case T(1) = 1, breaking down what each term represents.

We can translate that three-step breakdown directly into the language of mathematics. Let T of n represent the total number of moves required to transfer a stack of n disks. To solve for n disks, we first move n minus 1 disks to the auxiliary peg, which takes T of n minus 1 steps. Then we move the single largest disk with one decisive step. Finally, we move those n minus 1 disks from the auxiliary peg onto the target peg, taking another T of n minus 1 steps. This gives us our recurrence relation, T of n equals two times T of n minus 1 plus one, anchored by the simple base case where T of one equals one.

## 6 - Unrolling the Recurrence
> ANIM: Show the algebraic expansion of T(n) = 2(2T(n-2) + 1) + 1 down to the geometric series summation 1 + 2 + 4 + ... + 2^(n-1).

We can uncover the true growth rate of this process by unrolling the recurrence algebraic step by step. Substituting the formula into itself, T of n expands into two times the quantity two times T of n minus 2 plus one, plus one, which simplifies to four times T of n minus 2 plus two plus one. Continuing this expansion down through k steps reveals a pattern of powers of two. The resulting expression becomes a geometric series consisting of one plus two plus four, continuing all the way up to two to the power of n minus one.

## 7 - Exponential Complexity and Scale
> ANIM: Display a graph of O(2^n) versus n, plugging in n = 64 to show the astronomical number of moves and time required to complete the mythic puzzle.

That geometric series explodes in magnitude as the number of disks increases. When we plug the mythic sixty-four disks into our formula two to the power of n minus one, the total number of required moves reaches an astronomical eighteen quintillion. Even if the temple monks executed one move every single second without stopping to rest, completing the puzzle would take hundreds of billions of years. The exponential time complexity of O of two to the power of n means that brute force is utterly useless for large inputs, making elegant logic our only tool for survival.

## 8 - Writing the Recursive Algorithm
> ANIM: Display a clean pseudocode block for hanoi(n, source, target, auxiliary), tracing the recursive calls for n = 3 and asking what problem we solve next with tree recursion.

We can implement this elegant logic directly in code with a remarkably short function. The algorithm takes the number of disks along with the source, target, and auxiliary pegs as arguments, recursively calling itself to shift the upper stack before moving the final disk. Tracing this function for three disks cleanly mirrors the manual steps we performed earlier. But as we look at how these function calls branch out and mirror one another in memory, we have to ask what other complex problems we can solve next using tree recursion.

