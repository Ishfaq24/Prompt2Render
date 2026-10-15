---
title: Linked Lists in Five Minutes
topic: linked lists in data structures and algorithms
audience: undergraduate computer science
aspect: 16:9
voice: am_eric
---

## 1 - Why Not Just Use an Array?
> ANIM: Show an array containing 12, 99, and 37, then insert 45 in the middle and shift the later values.

Arrays are excellent when we need instant access by index. Their values sit next to one another in memory, so the address of index two is easy to calculate. But that same contiguous layout makes updates expensive. To insert 45 between 12 and 99, every later value must move one position. If the array is full, the computer may need to allocate a larger block, copy every value, and release the old block. Linked lists make a different trade: their nodes may live anywhere in memory, as long as each node remembers where the next one is.

## 2 - The Anatomy of a Node
> ANIM: Split one node into a data field and a next pointer, then draw the pointer toward another memory address.

A linked list starts with a node. A node has two important fields. The data field stores the value, such as 12. The next field stores a reference to another node, such as address 0x04F2. That reference is not the next value itself. It is the location where the next node can be found. This extra pointer is the price of flexible storage. Instead of relying on physical neighbors, the program follows logical neighbors. A list is therefore a chain of small records distributed through memory.

## 3 - Head, Links, and Null
> ANIM: Build the chain 12 to 99 to 37, add a head pointer, and finish the last link with null.

To enter the chain, we keep a pointer called head. Head points to the first node, 12. The next field in that node points to 99, and 99 points to 37. The last node has no successor, so its next field contains null. Null is the boundary marker that tells an algorithm the chain is finished. Notice what makes this structure powerful: the nodes do not need consecutive addresses. The links preserve the order even when the physical locations are scattered.

## 4 - Traversing the Chain
> ANIM: Move a current pointer from 12 to 99 to 37, highlighting one node at a time.

A linked list does not support direct indexing in the usual sense. To reach the third value, we cannot jump straight to it. We create a temporary pointer named current and set it to head. We read 12, follow its next link, and move current to 99. Then we follow the next link again and arrive at 37. We continue until current is null. This is traversal: a sequential walk through the references. It takes linear time, O of n, because the list may require visiting every earlier node.

## 5 - Inserting a Node
> ANIM: Insert node 45 between 99 and 37 by changing two arrows without moving existing nodes.

Now the advantage becomes visible. To insert 45 between 99 and 37, first create the new node. Set 45's next pointer to 37. Then replace 99's next pointer so it points to 45. The existing nodes never move. Only two references change, so once we already know the insertion position, the update is constant time, O of 1. Inserting at the front is also O of 1: make the new node point to the current head, then move head to the new node.

## 6 - Deleting and the Trade-off
> ANIM: Remove 99 and bypass it with a direct link from 12 to 37, then compare array and linked-list costs.

Deletion follows the same idea. To remove 99, find its predecessor, 12, and make 12 point directly to 37. The removed node is bypassed and can be reclaimed. But finding that predecessor may require traversal, so the complete operation is not automatically O of 1. Linked lists are fast when the location is already known, while arrays are fast for random access. An array usually needs O of 1 access and low overhead. A linked list usually needs O of n access and an extra pointer per node.

## 7 - Variations and Recap
> ANIM: Show a comparison table, then add previous pointers to transform a singly linked list into a doubly linked list.

The central lesson is a trade-off. Arrays favor indexing and compact storage. Linked lists favor growth and local insertion or deletion. A singly linked list moves forward through next pointers. A doubly linked list adds a previous pointer, making backward traversal possible but using more memory and requiring more links to maintain. Choose the structure based on the operations your program performs most often. Remember the chain: data plus a reference, head at the beginning, null at the end, sequential traversal, and constant-time rewiring when the position is known.
