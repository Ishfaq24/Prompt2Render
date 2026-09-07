---
title: The Euclidean Algorithm: Finding the Greatest Common Divisor
topic: How the Euclidean algorithm computes the greatest common divisor using iterative remainder division and logarithmic complexity
audience: undergraduate computer science and mathematics students
---

## 1 - The Core Mathematical Insight
> ANIM: Use SplitStage showing two numbers A=252 and B=105 on the left and the fundamental theorem gcd(a, b) = gcd(b, a mod b) on the right inside a FormulaCard.

The Greatest Common Divisor of two integers is the largest positive number that divides both without leaving a remainder. In 300 BC, Euclid proved a profound theorem: the greatest common divisor of two numbers does not change if you replace the larger number by its remainder when divided by the smaller number.

## 2 - Step-by-Step Remainder Reduction
> ANIM: Use HeroFocusStage displaying a FormulaCard with the exact arithmetic steps: 252 = 105 * 2 + 42, then 105 = 42 * 2 + 21, and finally 42 = 21 * 2 + 0, highlighting the last non-zero remainder 21.

Let's compute the GCD of 252 and 105. First, 252 divided by 105 gives quotient 2 and remainder 42. Next, we replace 252 with 105 and 105 with 42: 105 divided by 42 gives remainder 21. Finally, 42 divided by 21 gives remainder zero. Because the remainder is zero, the last non-zero remainder — 21 — is the exact greatest common divisor.

## 3 - Logarithmic Time Complexity and Lame's Theorem
> ANIM: Use BenchmarkStage displaying comparison cards for "Brute Force: O(min(a,b))", "Euclidean: O(log(min(a,b)))", and "Worst Case: Fibonacci Pairs".

Unlike naive brute-force division which tests every integer up to the smaller number, Euclid's algorithm shrinks the numbers exponentially. Gabriel Lamé proved that the maximum number of division steps is at most five times the number of digits in the smaller number, achieving lightning-fast logarithmic time complexity.

## 4 - Summary: The Engine of Modern Cryptography
> ANIM: Use HeroFocusStage centering the GCD algorithm connected to peripheral applications: "RSA Cryptography", "Modular Inverses", and "Diophantine Equations".

In summary, the Euclidean algorithm is more than an ancient geometric trick: it is the fundamental mathematical engine behind modern public-key cryptography, extended modular inverses, and efficient numerical computing.
