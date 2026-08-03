---
title: Cache Mapping - Direct vs Associative
topic: cache mapping schemes in computer organisation
audience: undergraduate computer science
---

## 1 - Why caches need a mapping rule
> ANIM: main memory blocks on the left, a small cache on the right

Main memory has millions of blocks. Your cache has maybe a few hundred lines. So the very first question any cache design must answer is simple: when block number four thousand arrives, which line does it go in?

## 2 - Direct mapping
> ANIM: modulo arrows from memory blocks into fixed cache lines

Direct mapping answers that with modulo arithmetic. Block number modulo the number of lines. It is fast and the hardware is trivial, because there is exactly one place to look.

## 3 - The conflict problem
> ANIM: two hot blocks colliding on one line, thrashing

But watch what happens when two frequently used blocks map to the same line. They evict each other on every access. The cache is mostly empty and still missing constantly.

## 4 - Set-associative as the compromise
> ANIM: cache split into sets of two ways, block placed in either way

Set-associative mapping splits the difference. Each block still maps to one set, but within that set it can sit in any way. Two hot blocks now coexist, and you only pay for a small comparison.
