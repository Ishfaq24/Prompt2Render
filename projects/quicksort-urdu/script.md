---
title: Quick Sort Algorithm
topic: Quick Sort, Divide and Conquer, Pivot Selection, Partitioning, Complexity
audience: undergraduate computer science
aspect: 16:9
language: en
audio_language: ur
burn_subtitles: false
---

## 1 - The Divide and Conquer Idea
> ANIM: ArrayGrid showing unsorted elements [29, 10, 14, 37, 13] with pivot selection highlight

کوئیک سورٹ ایک انتہائی تیز اور موثر تقسیم اور فتح کا الگورتھم ہے۔ اس کا بنیادی اصول یہ ہے کہ ہم فہرست میں سے ایک عنصر کو پیوٹ کے طور پر منتخب کرتے ہیں۔

## 2 - Partitioning Around the Pivot
> ANIM: SplitStage showing elements smaller than pivot on left and greater on right

پارٹیشننگ کے دوران، پیوٹ سے چھوٹے تمام عناصر بائیں جانب رکھے جاتے ہیں، اور بڑے عناصر دائیں جانب۔ اس طرح پیوٹ اپنی حتمی درست جگہ پر پہنچ جاتا ہے۔

## 3 - Recursive Sorting and Complexity
> ANIM: BenchmarkStage showing Best O(n log n), Average O(n log n), and Worst O(n^2) complexity

اس کے بعد دونوں ذیلی حصوں کو بار بار ریکرسیو طریقے سے ترتیب دیا جاتا ہے۔ کوئیک سورٹ کی اوسط وقت کی پیچیدگی او این لاگ این ہوتی ہے جو کہ انتہائی شاندار ہے۔
