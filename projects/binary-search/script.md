---
title: Binary Search: The Invariant Nobody Teaches
topic: binary search, its loop invariant, and its generalisation to monotone predicates
audience: undergraduate computer science
---

## 1 - A bug that lived in the JDK for nine years
> ANIM: title card naming binary search; then a stat card reading "90% of professional programmers could not write it correctly" (Jon Bentley, Programming Pearls); then a code line `int mid = (lo + hi) / 2;` with a red marker on the plus sign; then a card reading "shipped 1997, fixed 2006"

You already know binary search. Look at the middle, throw away half, repeat. It fits in a sentence, and it is the first algorithm most people can describe from memory.

Now the uncomfortable part. Jon Bentley set it as an exercise to groups of professional programmers, gave them a couple of hours, and found that about ninety percent of them wrote a version that was broken. Not slow. Broken.

And this is not a story about beginners. The binary search in the Java standard library shipped with a bug in nineteen ninety-seven, and it was not fixed until two thousand and six. Nine years, in code that ran on billions of devices, written and reviewed by very good engineers.

The bug was not in the idea. The idea is fine. The bug was in a single plus sign.

So this is not a video about how binary search works. It is about what the idea actually is, why describing it as "check the middle" is not enough to write it correctly, and where it goes once you stop thinking about sorted arrays.

## 2 - The idea is not the middle, it is the promise
> ANIM: a 16-cell sorted array with index labels; lo and hi pointer arrows under the first and last cells; a bracket over the live range labelled "the target is in here, or nowhere"; then successive probes where mid is marked, the discarded half is greyed out, and lo or hi jumps

Here is the reframe that makes the whole thing click.

Checking the middle is what the algorithm does. It is not what the algorithm is. What the algorithm is, is a promise you refuse to break.

The promise is this: if the target exists anywhere in the array, it is inside the range from lo to hi. Nowhere else.

At the start that promise is free. Set lo to the first index and hi to the last, and the range is the whole array, so of course the target is in there if it is anywhere at all.

Now every step has to do two things at once. It has to make the range strictly smaller, and it has to leave the promise still true.

Look at the middle element. If it is smaller than the target, then the middle and everything left of it are all too small, so the target cannot be there. Move lo to just past the middle. The range shrank, and nothing that could have been the answer was thrown away. The promise survives.

If the middle is larger, the mirror image. Move hi to just before the middle.

And if the range ever becomes empty, the promise is still true, and it now says something final: the target is inside an empty range, which means it does not exist.

That is the entire algorithm. Not a trick about halving. A guarantee you carry from the first line to the last, and every line of the loop is written to protect it.

## 3 - Why halving wins so hard
> ANIM: a table of array size against steps: one thousand to ten, one million to twenty, one billion to thirty, four billion to thirty-two; beside it two curves, linear rising steeply and logarithmic nearly flat, on the same axes

It is worth being precise about what you get for that.

With a linear scan, doubling the data doubles the work. That is the intuition everyone has, and it is correct.

With binary search, doubling the data adds one step. One. Not one percent more, not double: one single extra comparison.

So a thousand items take about ten steps. A million takes twenty. A billion takes thirty. Every record in a four billion row table, found in thirty-two questions.

Sit with that for a second, because it is genuinely strange. Going from a thousand rows to a billion rows multiplies your data by a million, and costs you twenty extra comparisons.

This is why the internals of almost every database index are built on this idea. Not because halving is clever, but because logarithms grow so slowly that they are very nearly free.

## 4 - The three ways it breaks
> ANIM: three numbered failure cards; card one shows `(lo + hi) / 2` overflowing past two-to-the-thirty-one with a red wrap-around arrow, then the fix `lo + (hi - lo) / 2`; card two contrasts a closed range with a half-open one; card three shows a two-element range where lo equals mid so the range never shrinks, looping forever

Now the failures, because knowing the invariant tells you exactly where they come from.

The first is the Java bug. To find the middle you add lo and hi and divide by two. That addition is the problem. On a large array, lo plus hi can exceed the largest number a signed thirty-two bit integer can hold, and it wraps around to a negative value. You then index an array with a negative number and the whole thing dies. The fix is to compute lo plus the quantity hi minus lo, divided by two. Mathematically identical. Never overflows, because the difference is never bigger than the array.

The second is the boundaries. Does hi point at the last valid element, or one past it? Both conventions work. Mixing them does not. If hi is the last valid index your loop runs while lo is less than or equal to hi. If hi is one past the end, it runs while lo is strictly less than hi. Pick one, write down what your range means, and the comparison follows from it rather than from guessing.

The third is the infinite loop. Integer division rounds down, so when only two elements are left, the middle is the left one. If your update sets lo to mid rather than mid plus one, the range stops shrinking. It is still correct, in the sense that the promise still holds. It just never ends.

And notice the pattern. Every one of these is a failure of the same thing. Either the range stopped shrinking, or the promise stopped being true. Nothing else can go wrong.

## 5 - Binary search without an array
> ANIM: a strip of cells reading false, false, false, false, true, true, true with the boundary between the last false and the first true marked "the answer"; then three examples labelled square root, git bisect, and minimum ship capacity, each mapped onto the same strip

Here is the part that turns this from an exercise into a tool you reach for constantly.

Nothing in that argument actually required a sorted array. What it required was a question whose answer flips from no to yes exactly once as you move along.

Picture a row of answers to some yes-or-no question. No, no, no, no, yes, yes, yes. If it never flips back, you can find that boundary in logarithmic time, using precisely the reasoning we just built.

Sorted arrays are just one instance. "Is this element at least as large as my target" flips from no to yes exactly once, which is why the array version works at all.

But so does this. Is this number squared bigger than the value I want the root of? No, no, no, yes, yes. Binary search gives you square roots.

Is this commit broken? Working, working, working, broken, broken. That is git bisect. It is binary search over your history, and it finds the commit that broke the build in about ten steps instead of a thousand.

Can I ship all the packages in D days if each truck holds this much? Too small, too small, big enough, big enough. Binary search on the answer.

So the real skill is not memorising the loop. It is learning to recognise that shape: a question that flips once. When you see it, you already know the algorithm.

Which raises the obvious next question. What happens when the question does not flip cleanly, when the data is sorted but rotated, or has duplicates, and the boundary is no longer unique? That is where we start next time.
