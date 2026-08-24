---
title: Computing Pi: From Polygons to Infinite Series
topic: definition of pi, Archimedes' method of exhaustion, Gregory-Leibniz series, convergence rates, Machin-like formulas, Bailey-Borwein-Plouffe spigot algorithm
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

## 1 - Why Does a Simple Circle Defy Decimal Precision?
> ANIM: A circle with diameter equal to one unrolls its circumference onto a continuous number line, halting at a coordinate that generates an infinite, non-repeating stream of decimal digits.

Why does something as simple as a circle defy exact decimal representation? When we take a circle with a diameter equal to one and straighten its curved boundary into a linear path, the total length refuses to land on a clean terminating value. Instead, the boundary stretches out and places a marker at a coordinate that immediately triggers an infinite and non-repeating sequence of decimal digits. This fundamental irrationality means that no matter how much memory we allocate, a computer can never store the complete value of pi using standard finite representations. We are forced to rely on approximations, algorithms, and infinite processes to get closer to a target that always stays just out of reach.

## 2 - The Failure of Physical Measurement
> ANIM: A schematic showing a caliper measuring physical cylinders of various sizes, with a table illustrating how mechanical tolerances and measurement errors limit the precision of the ratio to three decimal places.

Relying on the physical world to resolve this mathematical constant introduces immediate roadblocks. When we try to determine the ratio of a circle by taking physical measurements of manufactured cylinders, our tools inevitably run up against mechanical tolerances. Calipers and micrometers introduce thermal expansion, surface imperfections, and systematic measurement errors that quickly corrupt our data. No matter how carefully we machine the metal, these physical constraints cap our experimental precision at a meager three decimal places. To push past this barrier and extract millions or trillions of digits, we must abandon physical measurement entirely and step into the realm of pure computation.

## 3 - Archimedes' Algorithm: Bounding with Polygons
> ANIM: A circle nested between an inscribed hexagon and a circumscribed hexagon, which dynamically increase their side counts to 12, 24, and 96 to squeeze the upper and lower mathematical bounds of pi.

The earliest systematic way to bypass physical limitations relies on pure geometry by trapping the constant between two enclosing boundaries. If we place a polygon entirely inside a circle and another polygon entirely outside of it, the true value of the ratio must lie somewhere in the narrow gap between their perimeters. We can begin this process with a simple six-sided hexagon. As we systematically double the number of sides to twelve, twenty-four, and finally ninety-six, the inner and outer polygons press tighter and tighter against the curved edge. Each doubling step updates our mathematical bounds, squeezing the allowable range for pi into an increasingly narrow window of certainty.

## 4 - The Infinite Series Shift: Leibniz's Formula
> ANIM: An algebraic display of the Gregory-Leibniz alternating series alongside a line graph that plots its painfully slow, oscillating convergence toward pi over four.

Geometric exhaustion eventually becomes painfully slow, prompting a massive shift toward algebraic infinite series. Instead of drawing polygons, we can express the constant as the infinite sum of a sequence of numbers that march onward forever. The Gregory-Leibniz formula offers a strikingly simple pattern of alternating additions and subtractions using odd denominators. However, when we plot the running total of this series on a line graph, we discover a severe computational penalty. The curve oscillates wildly back and forth, creeping toward the true target with agonizing slowness. Achieving high precision with this formula requires millions of individual arithmetic operations, making it entirely impractical for serious computational work.

## 5 - Optimizing Convergence: Machin's Breakthrough
> ANIM: The mathematical formula \frac{\pi}{4} = 4 \arctan\left(\frac{1}{5}\right) - \arctan\left(/\frac{1}{239}\right) is displayed alongside the Taylor series expansion \arctan(x) = x - \frac{x^3}{3} + \frac{x^5}{5} - \dots. Below them, a side-by-side execution trace highlights how substituting $x = 1/5$ generates powers of $1/25$ per term step, showing the rapid decay of terms compared to Leibniz's series.

To make serious headway in computation, we need a mathematical identity that converges rapidly instead of dragging its feet. John Machin solved this problem by combining inverse tangents into a clever identity: pi over four equals four arctan of one-fifth minus arctan of one two-hundred-and-thirty-ninth. By displaying the underlying Taylor series expansion $\arctan(x) = x - \frac{x^3}{3} + \frac{x^5}{5} - \dots$, we can visually map how substituting $x = 1/5$ leads directly to powers of $1/25$ per term step. Because these arguments are small fractional values, the terms in their expansions decay exponentially, speeding up convergence. When we run a side-by-side execution trace comparing Machin's formula against the sluggish Leibniz series, the difference in computational efficiency is staggering. While Leibniz requires countless terms to budge the tenth decimal place, Machin's formula arrives at high precision with only a handful of rapid iterations. This breakthrough transformed the calculation of pi from an endurance test into an efficient algorithmic task.

## 6 - The CS Twist: Extracting Digits with BBP
> ANIM: A memory tape diagram and formula display showing the BBP formula $\pi = \sum \frac{1}{16^k} \left( \frac{4}{8k+1} - \frac{2}{8k+4} - \frac{1}{8k+5} - \frac{1}{8k+6} \right)$. An animation demonstrates multiplying the sum by $16^n$, splitting terms into whole and fractional parts, and evaluating the fractional parts via modular exponentiation to extract the millionth hexadecimal digit.

Modern computer science takes this efficiency a step further by decoupling precision from sequential dependency. The Bailey-Borwein-Plouffe spigot algorithm changes the rules of the game by allowing us to extract specific digits of pi directly using the formula $\pi = \sum \frac{1}{16^k} \left( \frac{4}{8k+1} - \frac{2}{8k+4} - \frac{1}{8k+5} - \frac{1}{8k+6} \right)$. Multiplying this sum by $16^n$ allows us to split the sum into a whole part and a fractional part. We can then compute the fractional part of each term modulo $8k+j$ using binary left-to-right modular exponentiation in $O(\log n)$ time. This means a memory tape can compute the exact value of the millionth hexadecimal digit without ever calculating any of the preceding digits, demonstrating how clever mathematical structuring can optimize memory usage and processing time.

## 7 - From Geometry to Bits: The Next Challenge
> ANIM: A chronological roadmap summarizing the shift from geometric exhaustion to infinite series to modern spigot algorithms, ending with a question mark over how modern supercomputers calculate trillions of digits.

From the physical constraints of drawn polygons to the slow march of infinite series and the direct extraction of bits in modern spigot algorithms, the quest to compute pi has continually driven mathematical and computational innovation. Each historical shift has traded slow physical or geometric methods for sharper algebraic tools and more efficient data manipulation. Yet, as algorithms grow more sophisticated, the scale of computation grows even faster. How do modern supercomputers push these limits to calculate trillions of digits without running out of memory or precision?

