---
title: Tower of Hanoi: Recursion and Exponential Growth
topic: Tower of Hanoi - recursive problem decomposition, recurrence relations, exponential time complexity O(2^n), binary and bitwise solutions
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; ~15 min total = ~2100 words
     across 9 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build. -->

## 1 - Moving sixty-four disks
> ANIM: A graphic shows three peg towers with 64 stacked disks on the first peg, accompanied by a text counter of total moves required: 18,446,744,073,709,551,615.

Imagine a legendary monastery where monks must transfer a tower of sixty-four golden disks between diamond pegs following strict rules. Moving that complete tower requires an astronomical number of individual steps. It totals over eighteen quintillion separate moves. If the monks completed one move every single second without stopping, the task would take hundreds of billions of years. We need a fundamental shift in how we think about scale to understand why this problem grows so rapidly.

## 2 - The three-disk base case
> ANIM: Trace moving 3 disks from Peg A to Peg C: show the exact sequence of 7 steps using smaller sub-problems of moving 2 disks.

We can build our intuition by scaling the puzzle down to just three disks on the first peg. Moving these three disks to the third peg requires a precise sequence of seven steps. First, we move the top disk from peg A to peg C. Next, we move the second disk from peg A to peg B. Then, we place the first disk from peg C on top of the second disk on peg B. This frees our largest disk on peg A, allowing us to move it directly to the empty peg C. Finally, we repeat our three-step process to shift the two smaller disks from peg B onto our largest disk on peg C.

## 3 - Defining the recursive step
> ANIM: A diagram splits the n-disk problem on Peg A into three sub-tasks: move n-1 disks to B, move bottom disk to C, move n-1 disks from B to C.

This pattern reveals the core of recursive problem decomposition. To move any stack of n disks from our source peg to our target peg, we temporarily treat the top n minus one disks as a single unit. We shift that entire upper stack out of the way onto our auxiliary peg. That frees our largest bottom disk, allowing us to slide it directly to the target peg. Once the bottom disk is secure, we take the n minus one disks sitting on the auxiliary peg and shift them onto the target peg.

## 4 - Writing the recurrence relation
> ANIM: An equation block builds T(n) = 2T(n-1) + 1 step by step, highlighting the base case T(1) = 1.

We can translate this exact choreography into a mathematical recurrence relation. Let T of n represent the total number of steps required to move n disks. Moving the top n minus one disks takes T of n minus one steps. Moving the single bottom disk takes exactly one step. Then moving the n minus one disks again takes another T of n minus one steps. Combining these parts gives us our recurrence equation: T of n equals two times T of n minus one plus one. Our base case is trivial, because moving a single disk T of one requires just one step.

## 5 - Unrolling the recurrence
> ANIM: A tree diagram expands T(n) down to T(1), showing the doubling number of operations at each level summing to 2^n - 1.

We can unroll this recurrence relation to see the total work accumulate level by level. Expanding T of n substitutes our formula repeatedly, generating two times T of n minus two plus two plus one. As we trace this down to the base case, the number of operations doubles at every single level of our expansion. Summing these operations across all n levels yields a total of two raised to the power of n minus one total steps. This geometric series proves that the cost of the puzzle doubles with every single disk we add.

## 6 - The recursive algorithm in code
> ANIM: A syntax-highlighted Python function hanoi(n, source, target, auxiliary) executes live for n=3, updating a call stack visualization.

We can implement this logic directly in code using a simple recursive function that accepts the disk count, source, target, and auxiliary pegs. When the function runs for three disks, the call stack grows and unwinds in real time. The computer pauses each outer function call while it resolves the inner sub-problems. Each activation record holds its own local variables for the peg names. Once the base case executes, the return values cascade back up the stack, printing each required move in the exact correct order.

## 7 - The surprising binary pattern
> ANIM: A table lists the disk movement sequence for n=3 alongside binary numbers 001 through 111, revealing a direct mapping to the Gray code sequence.

A surprising mathematical pattern emerges when we write down the sequential disk movements for our three-disk puzzle. If we assign a binary digit to each step, the resulting sequence of bit patterns matches the classic Gray code. In this sequence, exactly one bit flips with every single transition from one step to the next. This means the Tower of Hanoi is not just a puzzle about stacked disks. It is a physical manifestation of reflected binary code and bitwise state changes.

## 8 - Iterative solutions without recursion
> ANIM: A state diagram shows the simple rule-based movement of the smallest disk every odd step, completing the puzzle without a call stack.

Because every move in the puzzle follows strict deterministic rules, we can solve the entire sequence iteratively without relying on a call stack. We simply alternate between two rules until every disk reaches the target peg. The first rule dictates that we always move the smallest disk to its next valid peg in a fixed rotational direction. The second rule dictates that we make the only other valid move available on the board, which never involves the smallest disk. This simple iterative approach completes the entire puzzle using only bitwise operations and a single loop.

## 9 - Summary and complexity limits
> ANIM: A complexity graph plots O(2^n) scaling steeply against polynomial growth, ending with the question: how do we solve problems where the search space itself grows exponentially?

Our complexity analysis confirms that the Tower of Hanoi demands exponential time, growing proportionally to two to the power of n. This scaling curve diverges rapidly from polynomial time algorithms, making large problem instances completely intractable for any computer. When faced with an exponential explosion of states, how do we solve problems where the search space itself grows too vast to compute?

