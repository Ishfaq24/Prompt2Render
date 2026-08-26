---
title: How Linked Lists Work in Memory
topic: linked lists - node anatomy, pointer references, sequential traversal, dynamic allocation vs contiguous arrays, head/tail pointers, O(1) insertion and deletion
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

## 1 - The Limits of Contiguous Memory
> ANIM: A contiguous array of integers [12, 99, 37] at addresses 0x01-0x03 attempts to insert an element at index 1, showing the costly shifting of subsequent elements and a blocked expansion at the end.

Why do we need a new way to store data when we already have arrays? Arrays are simple and fast because they store elements next to each other in a continuous block of physical memory. But this contiguous layout comes with severe limitations. Imagine we have an array containing the integers twelve, ninety-nine, and thirty-seven, located at consecutive memory addresses zero-one, zero-two, and zero-three. If we want to insert a new number at index one, we cannot just squeeze it in. We are forced to shift ninety-nine and thirty-seven to the right, one by one, to make room. This shifting takes time, especially as arrays grow larger. Even worse, if we want to add an element to the very end of the array, we might find our path blocked. If the next adjacent memory address is already occupied by another program's data, the array cannot expand. To grow, the computer must allocate an entirely new, larger block of memory elsewhere, copy every single element over to it, and release the old space. This process is highly inefficient and resource-intensive.

## 2 - Anatomy of a Node
> ANIM: A single node box splits visually into a data field containing '12' and a pointer field containing the hexadecimal memory address '0x04F2' which draws an arrow to that address.

To solve the limitations of contiguous memory, we must abandon the requirement that our data sits side-by-side. Instead, we can scatter our data across any available locations in memory. But if our data is scattered, how do we keep track of where everything is? We do this by wrapping each piece of data inside a structure called a node. A node is the fundamental building block of a linked list. Visually and conceptually, we can split a node into two distinct fields. The first field is the data field, which holds the actual value we want to store, such as the integer twelve. The second field is the pointer field. This field does not hold our data. Instead, it holds a raw memory address, such as zero-four-f-two. This address acts as a reference or a pointer, directing the computer to the exact location of the next node in the sequence. By pairing our data with a pointer, we create a way to link isolated chunks of memory together.

## 3 - Building the Chain in Memory
> ANIM: Three nodes with data [12, 99, 37] appear at non-consecutive memory locations, with arrows connecting them sequentially and a 'head' pointer pointing to the first node and a 'null' symbol terminating the last.

When we connect these individual nodes, we build a chain in memory known as a linked list. Let us look at how our numbers twelve, ninety-nine, and thirty-seven exist in this structure. Unlike the contiguous array, these three nodes are scattered across completely non-consecutive memory locations. To keep track of where the list actually starts, we use a dedicated pointer called the head. The head points directly to the first node containing twelve. The pointer field inside this first node contains the memory address of the second node, which holds ninety-nine. The pointer inside ninety-nine then points to the third node, containing thirty-seven. Because thirty-seven is the final element in our list, its pointer field does not contain a memory address. Instead, it holds a special value called null, which signifies the end of the chain. By starting at the head and following these pointers, we can navigate through the entire collection of data, even though it is fragmented across physical memory.

## 4 - Traversing the List
> ANIM: A 'current' pointer icon steps sequentially through the chain of nodes [12 -> 99 -> 37], highlighting each memory address reference as it hops from node to node.

Because the nodes are not stored next to each other, we cannot jump directly to a specific position in a linked list. Instead, we must perform a process called traversal. To traverse the list, the computer sets up a temporary tracking pointer, which we can call the current pointer. We initialize current to point to the head of the list, which is the node containing twelve. To move forward, the computer reads the pointer field of the node we are on, finds the memory address of the next node, and hops the current pointer to that address. Now, current points to ninety-nine. We repeat this step, reading the pointer field of ninety-nine to hop to the node containing thirty-seven. When the computer reads the pointer field of thirty-seven and detects the null value, it knows we have reached the end of the list and terminates the traversal. This sequential hop-by-hop process is the only way to navigate a basic linked list.

## 5 - O(1) Insertion in Action
> ANIM: A new node [45] is inserted between [99] and [37] by updating the pointer values and redirecting the graphical arrows without moving any existing nodes in memory.

While traversing a list requires work, inserting new elements is incredibly fast and efficient. Let us say we want to insert a new node containing the integer forty-five between the nodes ninety-nine and thirty-seven. In an array, this would require shifting elements and possibly reallocating memory. In a linked list, we do not have to move any existing nodes in memory at all. First, we allocate memory for our new node forty-five. Next, we set the pointer field of this new node to point to thirty-seven, which is the node that should follow it. Finally, we update the pointer field of ninety-nine so that it points directly to our new node forty-five instead of thirty-seven. By simply rewriting these two pointer values, the new node is instantly spliced into the chain. Because this operation requires the same number of steps regardless of how large the list is, we say that insertion in a linked list has a time complexity of constant time, or oh-of-one.

## 6 - The Tradeoff: Search vs Memory Overhead
> ANIM: A side-by-side comparison displays an array accessing index 2 instantly versus a linked list traversing to index 2, while a bar chart illustrates the extra memory overhead used by the pointer fields.

Of course, these benefits come with significant tradeoffs. To understand them, let us compare the linked list directly with a traditional array. When it comes to accessing a specific element, like the value at index two, an array is incredibly fast. The computer can calculate the exact memory address of index two instantly and access it in constant time. A linked list, however, must traverse step-by-step from the head to index two, which takes linear time, or oh-of-n. Furthermore, linked lists have a hidden cost in terms of physical memory. In an array, we only store the actual data values. In a linked list, we must store the data and the pointer for every single element. This means that for a list of integers, we might use twice as much memory as an array just to store the connections. We are trading memory space and search speed for flexible insertion and deletion.

## 7 - Beyond Single Links
> ANIM: A recap matrix compares array and linked list complexities, then morphs the single-pointer arrows into bidirectional arrows, hinting at doubly linked lists and trees.

To summarize, arrays give us instant access and low memory overhead, but make insertion and deletion slow and difficult. Linked lists give us highly efficient insertions and dynamic growth, at the cost of slower search times and extra memory for pointers. But what if we need to navigate our data backward as well as forward? The single pointers we have used so far only allow us to travel in one direction. To solve this, we can add a second pointer field to each node that points to the previous node, creating what is known as a doubly linked list. We can even point to multiple different nodes to build hierarchical structures like binary trees. This brings us to an important question: how do we modify our traversal algorithms when a node has multiple pointers to choose from, and how do we manage these complex connections without running into memory leaks?

