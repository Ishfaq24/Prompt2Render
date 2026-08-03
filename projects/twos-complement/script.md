---
title: Two's Complement: Why It Actually Works
topic: two's complement representation of signed integers
audience: undergraduate computer science
---

## 1 - There is no minus sign in a register
> ANIM: an 8-bit register drawn as eight switches, all zero; a minus sign appears above it and is struck out; then the bit pattern 11011011 with a question mark asking which number this is. Use exactly 11011011 for -37; do not use any other pattern.

A register is eight switches. Each one is on or off. That is the entire vocabulary, and nowhere in it is there a minus sign.

So when you write minus thirty-seven in C, something has to decide which of the two hundred and fifty-six possible switch settings means that. Not a symbol. A pattern.

Here is the pattern the machine in front of you actually uses: one, one, zero, one, one, zero, one, one. And the interesting part is not that it means minus thirty-seven. The interesting part is why that pattern, and not one of the other two hundred and fifty-five.

Because the answer is not that somebody picked it. Two's complement is the encoding that makes subtraction disappear. By the end of this you will be able to read the sign straight off any pattern, and more importantly you will know what the adder is doing when it never once checks whether your numbers are negative.

## 2 - The obvious idea, and the two ways it breaks
> ANIM: sign-magnitude layout with the top bit highlighted as the sign; show 00000001 as +1 and 10000001 as -1; then the two zeros 00000000 and 10000000 side by side; finally the column addition 00000001 + 10000001 = 10000010 with a red cross beside the result

The obvious idea is to do what we do on paper. Take the top bit and call it the sign. Zero for positive, one for negative. The other seven bits carry the size. That is sign-magnitude, and it is what most people invent when they first meet the problem.

It breaks in two places.

First, count the zeros. All eight bits off is zero. Top bit on, the rest off, is negative zero. Two patterns, one number. You have wasted a code, and every equality test now has a special case.

Second, and this is the one that kills it, addition stops working. Take plus one. Add minus one. Column by column, the way the hardware does it, with no idea what those bits are supposed to mean. You get one, zero, zero, zero, zero, zero, one, zero. Read that back as sign-magnitude and it says minus two.

So the circuit cannot just add. It has to look at the sign bits, decide whether this is really a subtraction, work out which operand is bigger, subtract the smaller from the larger, then reason about what sign to put on the result. That is a comparator and a subtractor and a pile of control logic sitting in the hottest path of your processor, and all of it exists only because of how you chose to write the numbers down.

## 3 - Let it wrap
> ANIM: the sixteen 4-bit patterns 0000 to 1111 arranged as a clock face; a pointer at 0000 steps backwards to 1111 then 1110; relabel the top half 0 to 7 and the bottom half -8 to -1; then show the definition two-to-the-n minus x

Now the idea that fixes everything.

Forget signs for a moment and watch what the counter does on its own. Sit at zero and count down by one. The hardware borrows, every bit flips, and you get all ones. Count down again: one, one, one, zero.

It wraps. Like an odometer rolling backwards past zero. Nobody had to build that behaviour. It is just what a fixed number of bits does when you run off the end.

So stop fighting it. Define negative x as the pattern you land on when you count down x times from zero. On n bits, that is two to the n, minus x.

That is the whole idea, and here is what it buys you. Adding is now the only operation you need. Plus one is zero, zero, zero, one. Minus one is one, one, one, one. Add them column by column and you get one, zero, zero, zero, zero. That leading one is a carry out of the top bit, and it falls off the end of the register, because the register is only four bits wide. What is left is zero, which is the right answer.

The carry falling off the end is not a bug you are ignoring. Dropping it is exactly the minus two to the n that turns the wrapped value back into the number you meant.

And you never work out two to the n minus x by hand, because there is a shortcut hiding inside it. Two to the n minus x is the same as two to the n, minus one, minus x, and then plus one. That middle term is a row of all ones minus your number, and subtracting a bit from one never borrows. It just flips it. So: invert every bit, add one. That is not a trick to memorise. It is the definition, rearranged until a circuit can do it in one pass.

## 4 - Minus thirty-seven, and the one number with no partner
> ANIM: worked example for -37 in 8 bits: 37 as 00100101, invert to 11011010, add one to reach 11011011; then verify 00100101 + 11011011 = 100000000 with the ninth bit visibly dropping off the register; finally a number line from -128 to +127 with 10000000 circled alone

Let us do the one from the start. Minus thirty-seven, eight bits.

Thirty-seven is thirty-two plus four plus one: zero, zero, one, zero, zero, one, zero, one. Invert every bit: one, one, zero, one, one, zero, one, zero. Add one: one, one, zero, one, one, zero, one, one.

That is the pattern I showed you three minutes ago.

Check it the only way that matters. Add it to positive thirty-seven. Every column carries, the whole way up, and you get a one followed by eight zeros. Nine bits. The ninth has nowhere to live, so it is discarded, and the register holds zero. Thirty-seven plus minus thirty-seven is zero, computed by an adder that never asked what sign anything was.

Two consequences worth carrying with you.

The range is lopsided: minus one hundred and twenty-eight through plus one hundred and twenty-seven. There is no plus one hundred and twenty-eight, because one pattern, a one followed by seven zeros, is its own negation. Invert it, add one, and you get it back unchanged. So the most negative integer has no positive partner, and negating it silently overflows. That is the bug underneath a surprising number of real crashes.

And the top bit still tells you the sign, but not because anyone declared it to be a sign bit. It reads as one for every wrapped value simply because wrapping lands you in the top half of the range. The meaning fell out of the arithmetic instead of being imposed on it.

Which leaves the obvious next question. If dropping the carry is what makes signed addition work, how does the processor tell the difference between a carry that should be dropped and a result that genuinely overflowed? That is the gap between the carry flag and the overflow flag, and it is where we start next time.
