---
title: How Self-Attention Works in Transformers
topic: self-attention mechanism, queries keys values, scaled dot-product, softmax attention weights
audience: undergraduate machine learning
---

## 1 - The Query, Key, and Value Projections
> ANIM: A sequence of word tokens ["The", "neural", "network"] passes through linear projection matrices W_Q, W_K, and W_V, generating distinct Query, Key, and Value vectors for each token in 2D vector space.

How do Transformer models understand the context of every word in a sentence simultaneously? The secret lies in the self-attention mechanism. For every token in an input sequence, such as the words "The", "neural", and "network", the model generates three distinct internal representations. These are the Query vector, the Key vector, and the Value vector. We can think of the Query as a specific question a word asks about its context. The Key acts as an identifier or index that describes what information a word has to offer. Finally, the Value vector holds the actual semantic content that will be extracted. These three vectors are created by multiplying the initial token embedding by three learned weight matrices, known as W-sub-Q, W-sub-K, and W-sub-V. By transforming each word into this three-part representation, the model prepares to measure how strongly every word relates to every other word in the sequence.

## 2 - Scaled Dot-Product and Softmax Scoring
> ANIM: Query vector Q1 computes dot products against Key vectors K1, K2, and K3, scales the scores by square root of d_k, and applies a Softmax normalization bar to generate attention probability weights.

Once the Queries, Keys, and Values are computed, the model calculates the compatibility between them using the scaled dot-product. To find out how much the first word should attend to the others, we take its Query vector and calculate the dot product against the Key vectors of all tokens in the sentence. When two vectors point in similar directions in embedding space, their dot product produces a high positive score. Next, we divide these raw similarity scores by the square root of the vector dimension, d-sub-k. This scaling step is crucial because it prevents the dot products from growing excessively large in high dimensions, which would cause the softmax gradients to vanish. Finally, we pass the scaled scores through a Softmax function. This normalizes the values into a clean probability distribution where all attention weights are positive and sum to exactly one.

## 3 - Contextual Aggregation and Output
> ANIM: The attention probability weights multiply each Value vector, and the weighted vectors sum together into a unified, context-rich Output vector Z1.

Now that we have computed the exact attention weights, the final step is to synthesize the contextualized representation. Each attention weight acts as a precision blend factor. We multiply each Value vector by its corresponding softmax attention weight. If a word is highly relevant to the Query, its Value vector receives a large weight; if it is irrelevant, its Value is scaled down toward zero. We then sum all of these weighted Value vectors together to produce the final output vector, Z-sub-one. Unlike the static input embedding we started with, this new vector is deeply infused with the meaning of the surrounding words. By repeating this process across multiple attention heads in parallel, Transformers capture syntax, long-range dependencies, and semantic nuance across entire documents at lightning speed.
