---
title: Hash Tables: How Lookups Get to O(1)
topic: hash tables - hash functions, collision resolution, load factor and resizing
audience: undergraduate computer science
---

## 1 - The hook
> ANIM: title card, then an 8-slot array drawn as empty boxes; a magnifying glass appears directly over box index 5 with a single straight arrow pointing into it - no scanning motion across the other boxes

Type a word into a dictionary app and the definition is just there. Not
"searching," not a spinner. There. And that word could have been any of a
few hundred thousand others.

Somewhere underneath, a program found the one entry you wanted without
looking at the ones you didn't. Not by being fast at checking. By not
checking at all.

That's a hash table. By the end of this you'll know exactly how a piece of
text turns into a place to look, and why that trick can also go wrong in a
way that's bitten real production systems.

## 2 - The naive approach and why it breaks
> ANIM: a list of eight names in an array being scanned one by one from the left with a pointer, counting up to 8; then the same eight names sorted alphabetically with a binary search halving the range down to one

Say what you'd try first. Keep the entries in a list and check them one at
a time until one matches. That works. It's also the whole problem: to find
one item you may have to look at all of them. Twice as many entries, twice
as long a wait. That's linear time, and it does not scale to the millions
of rows a real database or the tens of thousands of variables a real
compiler is tracking.

You can do better by keeping the list sorted and halving the search space
each step, the way you'd find a name in a phone book. That's logarithmic
time, a real improvement - a million entries drops to about twenty
comparisons instead of a million.

But twenty comparisons is still not zero, and it grows, just slowly, as
the table grows. And keeping the list sorted costs you every time you
insert something new - shift everything over to make room, or re-sort.
None of that goes away, it just gets cheaper per step.

What you actually want is to skip the comparisons entirely. Not search
faster. Not search at all.

## 3 - The key idea
> ANIM: a key, the string "cat", flowing into a labelled box "hash function"; the box outputs the number 5; an arrow from the number 5 lands directly on box index 5 of an 8-slot array, which lights up

Here's the idea that gets you there. Instead of asking "where in this list
is my item," compute where it is.

Take the key - the word, the username, whatever you're looking up - and
run it through a function that turns it into a number. Not a meaningful
number, not an ID anyone assigned it. Just an arithmetic mess of the key's
bits, chosen so that similar keys land on wildly different outputs. That's
a hash function, and the number it produces, reduced to fit your array size,
is an index.

Store the value at that index. To look it up again, don't search - hash the
key a second time, get the same number back, and go straight there. One
computation, one array access, done. That's the whole mechanism. Average
case, that's constant time: O(1). The size of the table barely matters,
because you never touch the entries you're not looking for.

The entire cost of a hash table lives in one guarantee: the same key always
hashes to the same number. Break that, and nothing else works.

## 4 - Worked example
> ANIM: an 8-slot array, empty; hash("cat") = 2 shown landing in slot 2; hash("dog") = 5 landing in slot 5; hash("owl") = 2 again, colliding with "cat" in slot 2; a small linked node for "owl" drawn chained off slot 2, pointing away from the array

Walk through it with three words and an array of eight slots.

Hash "cat," and say it comes out to 2. Slot 2 now holds cat. Hash "dog," it
comes out to 5. Slot 5 holds dog. Two lookups, two slots, no scanning.

Now hash "owl." Same function, same rules - and it also comes out to 2.
Two different keys, one slot. That's a collision, and with only eight slots
and an unbounded number of possible words, it is not a bug, it is a
certainty. This is where the "average case" in O(1) is hiding.

The fix used here is chaining: slot 2 doesn't hold one value, it holds a
tiny list. Cat is still first. Owl gets appended right after it in that
same slot. Looking up owl now costs two comparisons instead of one - still
nowhere near scanning the whole table, but not free either.

That's the trade the whole structure is built on. A good hash function
spreads keys thinly enough that most slots hold zero or one entries and
collisions stay rare and short. A bad one piles everything into a handful
of slots and you've quietly rebuilt the linear scan you were trying to
escape, one chain at a time.

Chaining isn't the only fix, either. Open addressing skips the linked list
and, on a collision, just probes forward to the next empty slot in the
array itself - slot 3, then 4, then 5 - and remembers to keep probing on
lookup too. No extra memory for pointers, but the table fills up faster and
probing gets longer as it does. Different trade, same underlying problem.

## 5 - Where this shows up in practice
> ANIM: a gauge labelled "load factor" with a needle sweeping from a green low zone toward a red zone near the top; beside it, an 8-slot array doubling into a 16-slot array with every existing entry re-hashed and redrawn into new positions

This isn't a theory exercise - it's the data structure under Python's
dict, JavaScript's object and Map, and every language's HashMap. Every one
of them is quietly running this same array-plus-hash-function design under
a much friendlier name.

Two things keep it fast in practice. First, load factor: the fraction of
slots that are occupied. Push that too high and collisions stop being rare
- chains get long and you're back to scanning. So implementations track it,
and once it crosses a threshold, usually around seventy percent, they
allocate a bigger array, often double the size, and re-hash every existing
key into a new slot. Expensive when it happens, but it happens rarely
enough that the average cost per insert stays constant.

Second, and this one is easy to miss: the hash function itself has to be
hard to reverse-engineer. If an attacker can predict which keys collide,
they can hand your server thousands of keys that all pile into one slot on
purpose, turning every one of your O(1) lookups into an O(n) scan at once.
That's not hypothetical - it's a real denial-of-service class, and it's why
production hash tables seed their hash function with randomness that
changes every time the program starts.

## 6 - Recap and the next question
> ANIM: recap card, three lines: "hash the key to an index", "collisions are certain, not rare - plan for them", "load factor triggers a resize"; then a padlock icon fading in beside the word "hash" with a question mark

Three things to keep. A hash function turns a key into an index, so lookup
becomes one computation instead of a search. Collisions aren't an edge
case, they're guaranteed once your key space is bigger than your table, so
every real hash table has a plan for them - chaining is one, there are
others. And load factor is the number that decides when the table has to
grow, trading an expensive rehash now for cheap lookups after.

That word "hash function" is doing more work than we gave it credit for
here - I treated it like a black box that just spreads keys around. Make
that box impossible to run backwards, and you don't just get a fast lookup
table. You get the one-way function underneath password storage and
digital signatures. That's next.
