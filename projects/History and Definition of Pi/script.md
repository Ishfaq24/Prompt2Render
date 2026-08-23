---
title: How Computer Science Redefined Pi
topic: definition of pi, Archimedes' method of exhaustion, infinite series convergence, spigot algorithms, Bailey-Borwein-Plouffe formula, computational complexity of digit extraction
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~13 min total = ~1820 words
     across 8 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - The Measurement Problem
> ANIM: A circle with diameter equal to one unrolls its circumference onto a flat number line, showing the point of contact settling between 3.14 and 3.15 with an overlay highlighting the impossibility of measuring this physical distance perfectly.

How do we compute a number we can never truly measure? If we take a circle with a diameter of exactly one unit and unroll its circumference onto a flat line, the point of contact settles somewhere between three point one four and three point one five. But if we zoom in, we find that physical measurements hit a wall. The atomic scale, experimental error, and the limits of our instruments make a perfect physical measurement of this distance impossible. Pi is not a physical constant we can extract from the real world with absolute precision. Instead, it is a mathematical structure. To know its digits, we must abandon physical measurement entirely and turn to computation.

## 2 - Archimedes and the Polygon Limit
> ANIM: A circle is nested between an inscribed and a circumscribed hexagon, which dynamically double their sides to 12, 24, and 96-gons as numerical upper and lower bounds squeeze closer around the value of pi.

The journey to compute pi began with geometry, specifically through Archimedes and his method of exhaustion. To pin down the value of pi, we trap a circle between two shapes we can easily measure: an inscribed hexagon on the inside and a circumscribed hexagon on the outside. This gives us an initial upper and lower bound. By doubling the number of sides to twelve, then twenty-four, and eventually ninety-six sides, the polygons cling tighter to the curve of the circle. The gap between the upper and lower bounds squeezes closer, trapping the value of pi within an increasingly narrow range. This is the earliest recorded iterative algorithm, showing that a continuous curve can be systematically bounded by discrete, linear steps.

## 3 - The Infinite Series Revolution
> ANIM: The Gregory-Leibniz infinite series is plotted on a graph, showing a step-by-step staircase approximation that oscillates wildy but slowly dampens toward the exact horizontal line of pi.

In the seventeenth century, the pursuit of pi shifted from geometric polygons to infinite series. The discovery of calculus allowed mathematicians to express pi as an infinite sum of fractions. One of the simplest examples is the Gregory-Leibniz series. If we plot its progress on a graph, we see a staircase pattern that oscillates wildly. It jumps far above pi, then drops far below it, slowly dampening as we add more terms. While beautiful, this series is a computational nightmare. It converges so slowly that calculating just a few correct decimal places requires thousands of additions and subtractions. For computer scientists, this highlighted a critical lesson: mathematical elegance does not always translate to algorithmic efficiency.

## 4 - The Computational Bottleneck
> ANIM: A dataflow diagram compares a traditional high-precision division algorithm requiring massive memory arrays to a stream-based memory-efficient pipeline.

As computers emerged, the challenge of calculating pi transitioned from human endurance to hardware limitations. If you write a naive program to calculate pi to millions of digits, you quickly hit a computational bottleneck. Traditional division algorithms require storing massive arrays of numbers in memory to maintain precision during long division. This high-precision arithmetic creates a heavy memory footprint, requiring gigabytes of random access memory just to hold intermediate states. Compare this to a stream-based pipeline, which processes data sequentially and minimizes active memory. This contrast illustrates the classic computer science trade-off between space complexity and time complexity when scaling algorithms to handle massive data sets.

## 5 - The Spigot Algorithm Breakthrough
> ANIM: An interactive trace shows Rabinowitz-Wagon's spigot algorithm, where an array of fractional state variables passes remainders to the right to output digits of pi sequentially without using high-precision arithmetic.

A major breakthrough in resolving this memory bottleneck came with the invention of the spigot algorithm, developed by Stanley Rabinowitz and Stan Wagon. Named after a dripping tap, a spigot algorithm outputs digits of pi sequentially, one by one, without requiring high-precision arithmetic or massive storage. The algorithm maintains an array of fractional state variables. As the computation progresses, it passes remainders from right to left across the array. The state updates in place, and a new digit drips out of the pipeline. Because it does not need to store the entire history of calculated digits, the spigot algorithm radically reduces the memory required to generate long streams of pi.

## 6 - The BBP Formula and Hexadecimal Extraction
> ANIM: The Bailey-Borwein-Plouffe mathematical equation is displayed, animating the fractional terms to show how a specific exponent mask isolates and extracts the n-th hexadecimal digit of pi without calculating any prior digits.

But what if you only want to know a specific digit of pi, say, the billionth digit, without calculating all the digits that come before it? For centuries, this was thought to be impossible. Then, the Bailey-Borwein-Plouffe, or BBP, formula redefined what was computationally feasible. This formula allows us to extract the n-th digit of pi in base sixteen, or hexadecimal, directly. By applying a mathematical exponent mask, the algorithm isolates the fractional part at a specific position. We can calculate this single hexadecimal digit in near-linear time and with almost no memory, bypassing the sequential dependencies of all previous algorithms.

## 7 - Complexity Classes of Pi Algorithms
> ANIM: A comparison table lists the Archimedean, Gauss-Legendre, and Chudnovsky algorithms side-by-side with their respective asymptotic time complexities per digit.

To understand the landscape of modern pi calculations, we must examine the complexity classes of different algorithms. The Archimedean method requires exponentially more effort for each additional digit of accuracy. Modern algorithms are vastly more efficient. The Gauss-Legendre algorithm achieves quadratic convergence, meaning the number of correct digits doubles with every single iteration, though it requires resource-intensive high-precision multiplication. The Chudnovsky algorithm, which powers modern world-record calculations, delivers roughly fourteen correct digits per term. Analyzing these algorithms side-by-side reveals how asymptotic time complexity, rather than raw CPU clock speed, determines our ability to reach trillions of digits.

## 8 - From Geometry to Bitstreams
> ANIM: A timeline visualizes pi's transition from a physical ratio to an analytic limit and finally to a pseudo-random bitstream generator, ending on a visualization of digit distribution to ask if pi is truly a normal number.

Over thousands of years, our understanding of pi has transformed from a simple geometric ratio into an analytic limit, and finally into a high-performance bitstream. Today, computer scientists treat the digits of pi as a source of pseudo-random data, testing modern hardware and parallel processing systems. If we analyze the distribution of these digits, they appear statistically random, yet they are generated by a completely deterministic formula. This leads to an intriguing open question in mathematics and computer science: is pi a normal number, where every finite sequence of digits is equally likely to occur?

