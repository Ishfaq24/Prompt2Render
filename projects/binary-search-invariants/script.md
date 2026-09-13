---
title: Binary Search: Invariants, Implementation, and Complexity
topic: binary search - sorted array requirement, search space invariants, midpoint calculation overflow bug, termination conditions, logarithmic complexity derivation, lower and upper bound variations
audience: undergraduate computer science
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.
     Aim ~140 spoken words per minute; ~15 min total = ~2100 words
     across 9 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build. -->

## 1 - The Linear Scanning Bottleneck
> ANIM: A visual timeline comparing an item lookup in an unsorted array of size 1,000,000 using step-by-step linear scan versus a sorted array partitioned by halves.

Searching an unsorted collection of one million elements leaves you no choice but to inspect every single value one by one. In the worst case, finding your item or proving it is missing takes one million comparisons. But if the data is sorted, every single comparison can tell you which half of the remaining space contains your target and which half can be discarded entirely. Instead of reducing the problem size by one element at a time, we eliminate fifty percent of all remaining possibilities in a single step.

## 2 - The Running Example and Loop Invariant
> ANIM: A sorted array of 9 integers [3, 8, 12, 17, 24, 31, 45, 62, 78] with explicit pointers L=0, R=8, and a search target of 45 highlighted.

Consider an array of nine sorted integers: three, eight, twelve, seventeen, twenty-four, thirty-one, forty-five, sixty-two, and seventy-eight. We want to search for the value forty-five. We establish two pointers, left at index zero and right at index eight. Our loop invariant guarantees that if the target exists anywhere in the array, it must lie within the inclusive interval bounded by left and right. Maintaining this guarantee across every iteration is what keeps our algorithm correct.

## 3 - Tracing Step 1: Halving the Array
> ANIM: Trace on [3, 8, 12, 17, 24, 31, 45, 62, 78] with target 45: compute mid index 4 (value 24), compare 24 < 45, and grey out indices 0 through 4 as L moves to 5.

To begin the search, we find the middle index between zero and eight, which gives index four. The value stored at index four is twenty-four. Because our array is sorted and twenty-four is strictly less than our target of forty-five, the target cannot exist at index four or anywhere to its left. We discard indices zero through four entirely and update our left pointer to index five. The search space is now reduced to the sub-array spanning from index five to index eight.

## 4 - Tracing Step 2: Isolating the Target
> ANIM: Trace on [3, 8, 12, 17, 24, 31, 45, 62, 78] with target 45: compute mid index 6 (value 45), compare 45 == 45, and return index 6 with a green success highlight.

With the left pointer at index five and the right pointer at index eight, we calculate the new midpoint at index six. The element at index six is forty-five. We compare our target to this value and find an exact match. The search terminates immediately and returns index six. In just two comparisons, we located our element within a space of nine items, without ever inspecting the other seven values.

## 5 - Tracing an Unsuccessful Search
> ANIM: Trace on [3, 8, 12, 17, 24, 31, 45, 62, 78] searching for missing value 15: show L and R narrowing until pointers cross (L > R), triggering loop termination.

Now suppose we search the same nine-element array for the number fifteen, which is not present. We start with left at zero and right at eight, checking midpoint index four, value twenty-four. Because fifteen is less than twenty-four, right becomes index three. The new midpoint is index one, value eight. Since fifteen is greater than eight, left becomes index two. The new midpoint between two and three is index two, value twelve. Fifteen is greater than twelve, so left advances to index three. Now left and right both equal three, pointing to seventeen. Fifteen is smaller than seventeen, so right becomes index two. Left is now greater than right, the valid search interval is empty, and the loop terminates, correctly reporting that the value does not exist.

## 6 - The Midpoint Arithmetic Overflow Bug
> ANIM: Side-by-side comparison of 32-bit signed integer representations showing (L + R) / 2 overflowing into negative values versus the safe form L + (R - L) / 2.

When calculating the midpoint between two indices, the intuitive formula is left plus right divided by two. In languages with fixed-width integers, this simple addition introduces a critical arithmetic overflow bug. If the sum of left and right exceeds the maximum positive value of a thirty-two bit signed integer, the sum wraps around into a negative number, resulting in an invalid negative index and a memory fault. To prevent overflow entirely, we rewrite the midpoint calculation as left plus the quantity right minus left divided by two.

## 7 - Deriving Logarithmic Time Complexity
> ANIM: A recursion tree diagram showing array size n being divided by 2 at each level, leading to n / 2^k = 1 and the formal derivation of k = log2(n).

To derive the time complexity formally, observe that each comparison divides the active search space by two. Starting with an initial size of n, after one step we have n divided by two elements remaining, after two steps n divided by four, and after k steps n divided by two raised to the power of k. The algorithm must terminate when the remaining search space is reduced to a single element. Setting n divided by two raised to the power of k equal to one and solving for k yields k equals log base two of n. This logarithmic scaling is why searching a billion items takes at most thirty comparisons.

## 8 - Handling Duplicates: Lower Bound Variants
> ANIM: A sorted array with duplicates [2, 5, 5, 5, 8, 11] showing how adjusting the equality branch shifts L and R to find the first occurrence of 5.

Standard binary search stops at the first matching element it encounters, which is unpredictable when the array contains duplicates. Consider the array two, five, five, five, eight, eleven, where we want to find the first occurrence of five. When our midpoint hits a matching five, instead of terminating, we treat the match as a signal to keep searching to the left by setting right equal to mid minus one. Recording the most recent valid match while continuing to shrink the window allows us to cleanly isolate the exact lower bound index of any repeated value.

## 9 - Recap and Search on Monotonic Functions
> ANIM: A summary card of pointer rules and O(log n) efficiency, transitioning into a continuous monotonic curve visual asking how to search without an explicit array.

Binary search achieves logarithmic efficiency because it requires only a consistent direction to eliminate half the candidates at each step. This means the underlying data does not actually have to be a physical array stored in memory. As long as any mathematical function or decision problem produces monotonic output, we can apply these exact same pointer invariants to search continuous domains or solve complex optimization problems. How do we structure binary search when we are searching over the answer space of a function rather than the indices of a list?

