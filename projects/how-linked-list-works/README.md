# Linked Lists in DSA

An end-to-end visual lesson on singly linked lists: node anatomy, scattered memory, traversal, insertion, deletion, complexity trade-offs, and the move to doubly linked lists.

## Render a scene

From the repository root:

```powershell
manim -pqh projects\how-linked-list-works\build\scenes\scene_01.py Scene01
```

Replace `scene_01.py` and `Scene01` with `scene_02.py` through `scene_07.py` for the other sections. The narration storyboard lives in `script.md`.

## Lesson map

1. Why arrays struggle with middle insertion
2. The two fields inside a node
3. Head, next pointers, and null termination
4. Sequential traversal with a current pointer
5. O(1) insertion by rewiring two links
6. Deletion and the search-versus-update trade-off
7. Complexity recap and doubly linked lists