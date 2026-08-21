---
title: Merge Sort: Splitting Your Way to O(n log n)
topic: merge sort - divide and conquer, the merge step, O(n log n) complexity, stability
audience: undergraduate computer science
---

## 1 - The hook
> ANIM: title card, then a row of 6 unsorted number tiles [5, 1, 4, 2, 8, 3]; a vertical line splits the row exactly in half into two groups of 3, then each half splits again into pairs, then singles - a tree shape falling open downward, one split at a time

Last time, sorting one comparison at a time, walking the whole row again
and again - and it cost you nearly the square of the input size. Here's
the other way in: instead of comparing neighbors, stop comparing for a
moment. Just split the pile in half.

Then split those halves in half. Keep going until every pile is a single
number - which is, trivially, already sorted. The entire trick left is
putting the pieces back together in order. That's merge sort, and it beats
the neighbor-swap approach so badly that no serious system sorts any
other way at real scale.

## 2 - The key idea
> ANIM: two small sorted arrays side by side, [1, 4] and [2, 5]; two pointers start at the front of each; the smaller of the two front values gets pulled down into a new empty row below, one comparison at a time, pointers advancing, until one side runs out and the rest gets copied down directly

The whole algorithm rests on one small, almost boring operation: merging
two already-sorted lists into one sorted list. Here's how that works.
Point at the front of each list. Compare the two values pointed at. Take
the smaller one, place it in the output, and move that one pointer
forward. Repeat.

Every comparison places exactly one value, permanently, into its final
spot - never revisited, never moved again. When one list runs out, the
other one is already sorted, so just copy whatever's left straight into
the output. Two sorted lists of size n become one sorted list of size 2n
in about 2n comparisons total. Linear work, for a merge.

So the plan is: split the array all the way down to single elements -
free, since one element is always sorted - then merge pairs back
together, then merge those results together, doubling the size each
round, until you're merging two halves of the whole array into one fully
sorted whole.

## 3 - Worked example
> ANIM: the array [5, 1, 4, 2, 8, 3] as 6 boxes; splitting downward into [5,1,4] and [2,8,3], then into [5],[1,4] and [2],[8,3], then all the way to six single boxes; then merging back upward - [1,4] and [4,5]... - wait, merges combining pairs level by level with values updating at each merge, ending in one fully sorted row [1,2,3,4,5,8] at the top

Six numbers: 5, 1, 4, 2, 8, 3.

Split down the middle: 5, 1, 4 and 2, 8, 3. Split each of those: 5 alone,
then 1, 4; and 2 alone, then 8, 3. One more split and everything is a
single number - six piles of one, and every one of them is sorted by
definition.

Now merge back up. Merge 1 and 4: compare, 1 is smaller, take it, then
only 4 is left, take it - result 1, 4. Merge 8 and 3: compare, 3 is
smaller, take it, then 8 - result 3, 8. One level up: merge 5 with 1, 4.
Compare 5 and 1 - take 1. Compare 5 and 4 - take 4. Only 5 is left - take
it: 1, 4, 5. Merge 2 with 3, 8. Compare 2 and 3 - take 2, then 3, then 8:
2, 3, 8.

Last merge: 1, 4, 5 against 2, 3, 8. Compare 1 and 2, take 1. Compare 4
and 2, take 2. Compare 4 and 3, take 3. Compare 4 and 8, take 4. Only 5
left on one side, then 8 - take both in order: 1, 2, 3, 4, 5, 8. Fully
sorted, built entirely out of merges of things that were already sorted.

## 4 - Why it's fast
> ANIM: a binary tree diagram, 6 elements at the top splitting down to 6 leaves of size 1 across log2(6) roughly 3 levels; beside each level, a label showing "n comparisons this level"; total labeled n times log n, next to a shrinking gap comparison against n^2

Count the work. Splitting the array in half, over and over, takes about
log base 2 of n rounds to get down to single elements - for a million
elements, that's only about twenty splits, because halving shrinks things
fast. That's the "log n" part.

Now count the merging. At every level of that split, no matter how many
piles there are, merging them all back together touches every element
exactly once - that's n comparisons per level, total, across the whole
level. Multiply: log n levels, n comparisons per level, and the total
work is n times log n.

For a million elements, n log n is around twenty million operations. The
neighbor-swap approach from last time was n squared - a trillion
operations on the same input. That gap, not some minor constant-factor
tweak, is why merge sort is a different category of algorithm, not just
a faster version of the same one.

## 5 - Where this shows up in practice
> ANIM: a small array of 5 named boxes, two of them sharing the same score; after merging, the same 5 boxes reordered by score with the two equal-score boxes still in their original left-to-right order relative to each other, marked with a "stable" badge; on its own line below, a short caption reading "chunks sorted on disk, merged back in - external sort"

Two properties make merge sort the default choice in places bubble sort
never gets near.

First: it's stable. Two elements that compare equal never swap past each
other, so if you sort a list of people by last name and two share a last
name, they stay in whatever order they were in before. That matters when
you're sorting by one field but care about a second one underneath it.

Second: merging doesn't need the whole array in memory at once, just the
two runs currently being combined. That's exactly the shape of external
sorting - sorting a file far bigger than RAM, in chunks, off disk. It's
also why merge sort splits cleanly across multiple machines: split the
data, sort each piece independently, merge the results. Python's built-in
sort and Java's Object sort are both variants of this idea for exactly
these reasons.

## 6 - Recap and the next question
> ANIM: recap card, three lines: "split in half until single elements", "merge sorted pairs back together, one comparison per element", "O(n log n) - log n levels times n work per level"; then a single array with a highlighted pivot element and arrows sweeping values to either side, with a question mark

Three things to keep. Merge sort splits the array in half, recursively,
until every piece is a single element. It merges those sorted pieces back
together two at a time, one comparison placing one element permanently.
And the total cost is n log n - log n levels of splitting, n comparisons
of merging at every level - which is why it beats the quadratic
neighbor-swap approach at any real size.

There's a cost hiding here too, though: merging needs extra space for
the output as you go, memory that neighbor-swapping never needed. Is
there a way to get n log n speed without paying for that extra array?
That's what quicksort answers next, and the answer involves picking one
element and asking a very different question about it.
