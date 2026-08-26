---
title: Why Floating-Point Pi Matters in Computer Science
topic: irrational constants, transcendental numbers, IEEE 754 precision limits, Leibniz series convergence, Chudnovsky algorithm, computational cost of high-precision math
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~9 min total = ~1260 words
     across 6 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - Why Can't We Store Pi Exactly?
> ANIM: Show a memory register overflowing while trying to fit an infinite decimal expansion of pi into a fixed 64-bit IEEE 754 float.

How do you store an infinite, nonrepeating sequence of digits inside a machine that only has room for a finite number of bits? You cannot. Pi is an irrational and transcendental number, meaning its decimal expansion goes on forever without a repeating pattern. When a computer tries to store this value, it runs straight into a hard physical and architectural wall. Under the standard IEEE seventy-five-four double-precision format, a floating-point number is carved up into a sign bit, an eleven-bit exponent, and a fifty-two-bit fraction. That leaves exactly fifty-three bits of precision to represent the entire value of pi. As the digits stream into the register, the system runs out of space. The bits overflow the allocated boundary, and the infinite tail is abruptly chopped off. That truncation is not just an aesthetic loss; it introduces an immediate rounding error. The moment pi is loaded into a hardware register, it ceases to be pi. It becomes a rational approximation, rounded to the nearest representable binary fraction, setting a permanent ceiling on the accuracy of every calculation that follows.

## 2 - Geometric Origins: Polygons and Exhaustion
> ANIM: An animation showing Archimedes inscribing and circumscribing polygons inside a circle, tightening bounds as sides increase from 6 to 96.

Long before electronic computers existed, mathematicians faced the challenge of pinning down the exact value of pi using geometry alone. Archimedes pioneered a method of exhaustion by inscribing and circumscribing regular polygons inside and outside a circle. Starting with a simple hexagon, with six sides, he doubled the number of sides step by step, forcing the perimeters of the inner and outer polygons to squeeze closer and closer to the true circumference of the circle. As the polygon grew from six sides to twelve, twenty-four, forty-eight, and finally ninety-six sides, the gap between the inner and outer bounds shrank dramatically. The perimeter of the ninety-six-sided inner polygon provided a lower bound of roughly three point one four zero, while the circumscribed polygon provided an upper bound of roughly three point one four eight. This bounding technique proved that pi was trapped in a very narrow interval. Yet, computing higher precision required pushing the polygon side counts into the thousands, revealing the physical and manual limits of geometric approximation.

## 3 - The Shift to Infinite Series
> ANIM: Display the Leibniz formula summing terms on a number line, visually demonstrating its agonizingly slow oscillation toward pi.

To bypass the grueling labor of drawing polygons with thousands of sides, mathematics shifted entirely from geometry to infinite series. Instead of shapes, mathematicians used infinite sums of fractions that slowly accumulate toward the value of pi. One of the most famous examples is the Leibniz formula, which alternates by subtracting and adding fractions over the odd integers. On a number line, the running total takes wild, swinging steps. The first term gives four. The second term subtracts four thirds, dropping the total down to two point six six. The next term adds four fifths, pushing the sum back up. With each successive term, the oscillation dampens, creeping by agonizingly small increments toward the true value of pi. The major drawback of this series is its brutally slow convergence rate. Reaching just a few decimal places of accuracy requires thousands of individual arithmetic operations, making naive infinite series entirely impractical for high-performance software.

## 4 - Rapid Convergence: The Chudnovsky Algorithm
> ANIM: Show a comparison table of decimal digits gained per iteration between Leibniz and the Chudnovsky formula used by modern supercomputers.

When modern supercomputers need billions of digits of pi, simple infinite series are completely useless. They instead rely on rapidly converging formulas, most notably the Chudnovsky algorithm. A direct comparison reveals the massive performance gulf between computational approaches. While the Leibniz formula crawls at a glacial pace, gaining only one correct decimal place for every ten terms computed, the Chudnovsky algorithm explodes forward with staggering efficiency. Each individual iteration of the Chudnovsky formula adds roughly fourteen new, correct decimal digits of pi to the running total. This hyper-exponential convergence stems from the clever use of Ramanujan-like hypergeometric series combined with large factorials. Because every single loop multiplies the precision pool by a factor of fourteen, a supercomputer running this algorithm can compute trillions of digits in a matter of hours, turning what was once a lifetime of manual labor into a brief routine exercise for modern hardware.

## 5 - Precision Limits in Software
> ANIM: A code snippet in Python or C showing a precision loss bug when computing area with standard floats versus arbitrary-precision libraries.

High-precision mathematics is not just a game for supercomputers; ignoring precision limits in everyday software leads to catastrophic failures. Consider a standard Python or C program tasked with computing the area of a circle using the standard float type. When the code multiplies the radius squared by the built-in floating-point approximation of pi, the rounding errors inherent in the fifty-three-bit register propagate through the multiplication. For a small radius, the error is negligible. But as the numbers grow or the operations compound, those microscopic discrepancies snowball. In worst-case scenarios, standard floats lose significant digits entirely, resulting in massive spatial or financial calculation bugs. To prevent this, software developers must abandon standard hardware primitives and import arbitrary-precision arithmetic libraries. These specialized libraries store numbers as dynamic arrays rather than fixed registers, trading raw hardware speed for exact mathematical fidelity.

## 6 - What Comes Next
> ANIM: A preview graphic of a floating-point number line highlighting rounding errors, leading to the question of how computers handle transcendental functions overall.

Standard floating-point numbers force a constant compromise between storage size and numerical accuracy, shaping every calculation executed inside modern processors. Even basic arithmetic operations introduce microscopic rounding errors that accumulate silently across complex codebases. When computers evaluate transcendental functions, those compounding discrepancies dictate the ultimate limits of simulation, graphics, and scientific modeling. Understanding how precision decays across a number line exposes the hidden fragility beneath digital computation. This inherent limitation naturally leads to a broader question about how processors handle complex mathematical functions as a whole.

