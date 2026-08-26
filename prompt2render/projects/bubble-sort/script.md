---
title: Bubble Sort: Why the Simplest Sort Is Also the Slowest
topic: bubble sort - adjacent swaps, passes, O(n^2) complexity, early-exit optimization
audience: undergraduate computer science
---

## 1 - The hook
> ANIM: title card, then a row of 6 unsorted number tiles; two adjacent tiles get a bracket around them and swap places with a short arc motion, then the bracket moves one step right - no other motion yet

Six numbers, in the wrong order. You want them sorted. Here's the laziest
possible idea: look at the first two, and if they're backwards, swap them.
Then look at the next two. Then the next. Just keep walking down the row
doing that.

It sounds too simple to work. It works. It's also, almost always, the wrong
way to sort anything - and understanding exactly why will tell you more
about algorithm cost than a faster sort ever could.

## 2 - The key idea
> ANIM: a row of array boxes with a two-cell bracket sliding left to right one step at a time; when the left value is bigger than the right, the two boxes swap with a curved arrow and both flash; otherwise the bracket just advances with no swap

This is bubble sort, and the whole algorithm is one rule, repeated: compare
two neighbors, and if the left one is bigger than the right one, swap them.
Then move one step over and do it again.

Walk that rule all the way to the end of the row, and something specific has
to happen - not maybe, has to. The single largest value in the whole array
gets compared against every one of its neighbors on the way, and every time
it's on the left of a comparison, it's bigger, so it swaps. It keeps getting
pushed right until it hits the end. One full pass guarantees the biggest
value is now sitting in the very last slot, correct, forever.

That's the "bubble" - not the small values bubbling up, the large one
sinking to the bottom, one comparison at a time. And once you see that one
pass fixes one slot, the rest of the algorithm is just: do another pass.

## 3 - Worked example
> ANIM: the array [5, 1, 4, 2, 8] shown as 5 boxes; walk pass 1 comparing indices (0,1) (1,2) (2,3) (3,4) one at a time with swaps drawn explicitly, ending with 8 locked in the last slot with a lock icon; then show pass 2 needing only 3 comparisons since the last slot is done

Take five numbers: 5, 1, 4, 2, 8.

Pass one. Compare 5 and 1 - out of order, swap: 1, 5, 4, 2, 8. Compare 5 and
4 - swap: 1, 4, 5, 2, 8. Compare 5 and 2 - swap: 1, 4, 2, 5, 8. Compare 5 and
8 - already in order, no swap. Four comparisons, three swaps, and the 8 -
the largest value - is now locked in the last position. It never has to be
touched again.

Pass two only needs to check the first four slots, since the last one is
settled. Compare 1 and 4 - fine. Compare 4 and 2 - swap: 1, 2, 4, 5. Compare
4 and 5 - fine. Now 5 is locked in second-to-last. Pass three: two
comparisons, sorts itself out to 1, 2, 4, 5. One more pass with zero swaps
confirms it's done.

Five elements. Four passes, each one shorter than the last, because every
pass shrinks the unsorted region by exactly one slot from the right.

## 4 - Why it's slow
> ANIM: a table with two columns - "array size" and "worst-case comparisons" - showing 10 -> 45, 100 -> 4950, 1000 -> 499500; beside it a curve labeled n^2 climbing steeply, next to a much flatter curve labeled n log n

Here's the bill. For an array of n elements, pass one does n minus one
comparisons. Pass two does n minus two. Pass three, n minus three. Add all
of those up and you get roughly n squared over two comparisons in the worst
case - a reversed array, where every single comparison forces a swap.

Double the input size and you don't double the work, you roughly
quadruple it. Ten elements, about forty-five comparisons - trivial. A
thousand elements, about half a million. A million elements, and you're
into the trillions. That's what O(n squared) means in practice: it doesn't
just get slower, it gets slower faster than the input grows.

Compare that to the n log n sorts - merge sort, quicksort - and the gap at
real sizes isn't small, it's the difference between milliseconds and
hours. That gap is the entire reason bubble sort isn't what any real
system uses.

## 5 - Where this shows up in practice
> ANIM: split screen - left side "nearly sorted array" with one out-of-place element and a single quick pass fixing it with an early-exit checkmark; right side a reversed array grinding through full passes with a warning badge

So why does bubble sort still show up in every algorithms course? Two
honest reasons.

First, one cheap fix makes it worth knowing: if a full pass makes zero
swaps, the array is already sorted, so you can stop early. On data that's
already almost in order - a mostly-sorted log file, a list with one new
entry appended - that turns an O(n squared) algorithm into something close
to O(n), one quick pass and done. That's not true of every simple sort.

Second, it's stable and it's in-place - equal elements never change
relative order, and it needs no extra memory beyond the array itself. Real
production code almost never reaches for it, but it's the cleanest possible
example of the tradeoff every sorting algorithm makes between simplicity,
memory, and speed - which is exactly why it's still the first one taught.

## 6 - Recap and the next question
> ANIM: recap card, three lines: "compare neighbors, swap if backwards", "one pass locks in one element from the end", "O(n^2) in general - O(n) if it's already nearly sorted"; then a silhouette of two sorted halves merging together with a question mark

Three things to keep. Bubble sort is one rule repeated: compare two
neighbors, swap if they're backwards. Each full pass guarantees one more
element - the current largest - locks into its final position from the
end. And the cost is quadratic in general, because every pass is only one
shorter than the last - though a single early-exit check makes it cheap on
data that's nearly sorted already.

That quadratic cost is the whole motivation for every sort that comes
after this one. The next trick isn't comparing neighbors one at a time -
it's splitting the array in half, sorting each half, and merging the
results back together. That's merge sort, and it's next.
