# Understanding How Self-Attention Works

## 1 - Introduction to Self-Attention & Generative AI
> ANIM: [manim] A cinematic dark background with glowing interconnected nodes representing a modern Neural Network. A vibrant title appears: "Understanding How Self-Attention Works". An illuminated hierarchy expands dynamically: Generative AI at the top, branching into the Transformer Architecture, zooming into the pulsing glowing core labeled "Self-Attention". Smooth camera transitions with elegant glowing labels.

Hi guys, my name is Ishfaq, and welcome to my channel.

Today, we are going to try to understand exactly how self-attention works.

Now, if I want to motivate you a little about why you should watch this entire video, I would just say one thing: I am pretty sure you are aware that, in today's market, a new technology called Generative AI has penetrated the industry.

Generative AI has become extremely important, and if you have given an interview recently, there is a good chance that you were asked questions around it.

There is clearly a growing demand in the industry around Generative AI.

And if I ask you: What is at the center of Generative AI technology? The answer should be the Transformer architecture.

The entire field of Generative AI is developing and improving around the Transformer architecture.

And if I ask you: What is at the center of the Transformer architecture? The answer is: Self-Attention.

That is why this video is extremely important. If you want to learn Generative AI, this is where your journey begins.

This video is so important that I have put an enormous amount of effort into it. Normally, it takes me two to three days to make a video, but this particular video took me 14 days to research, create, and shoot.

I don't think I have ever put this much effort into any other video on this channel. So, in that sense, this video is very special.

I have tried to explain self-attention in such a simple way that, by the end of this video, you should feel as if you invented self-attention yourself. That is a very ambitious level of simplification.

And I think this video will be successful for me if, at the end, you say: "Sir, I don't know why this took you 14 days. The topic was so simple!"

If it feels that simple to you after watching this video, then my job is done. So, I am really excited to see what your response is after watching this video. Let's start.

## 2 - Word Embeddings: The Static Flaw
> ANIM: [manim] Display text tokens: One-hot encoding, Bag of Words, Word Embeddings. Zoom into 2D vector space with coordinate axes showing static word vectors. Show two distinct sentences: "Money bank" and "River bank". An identical vector arrow labeled 'bank' appears in both sentences. Side-by-side comparison reveals 'financial institution' vs 'side of a river', highlighting the static limitation. A morphing animation introduces the concept: Static Embeddings e1, e2, e3 entering a Self-Attention Block and emerging as dynamic contextual embeddings y1, y2, y3.

Before starting today's video, let's quickly revise what we discussed in the last video. The topic of the last video was: What is Self-Attention?

We first discussed that whenever you want to build an NLP application, one of the most important things is to help machines understand how to represent words in the form of numbers.

This is where different techniques come into the picture, such as: One-hot encoding, Bag of Words, and Word embeddings.

Finally, we discussed word embeddings. We discussed that word embeddings are extremely useful because they can capture the semantic meaning of words and convert that meaning into numbers. That is the best part about word embeddings.

However, as we continued the discussion, we discovered a major problem with word embeddings: They are static.

What does static mean? Once you train a word embedding model, whenever you use a particular word, you will get the same embedding for that word everywhere.

Now, what is the problem with that? Suppose we have two sentences: "Money bank" and "River bank". I know these are not complete sentences. They are just examples to make the point.

In both sentences, the word "bank" is being used. But the context is completely different. Here, Bank equals financial institution, while here, Bank equals the side of a river.

But because we are using static word embeddings, the embedding of the word "bank" will be exactly the same in both places. And that is a problem. This cannot be a good starting point.

So what do we need? We need contextual embeddings. These embeddings should be dynamic and dependent on context.

If the word "bank" appears in the context of money, its embedding should contain one kind of information. If it appears in the context of a river, its embedding should contain different information.

And this is exactly where self-attention comes in. Self-attention provides a way to convert static embeddings into dynamic contextual embeddings.

Suppose we have the sentence: "Humans love smartphones." First, we take the static embeddings e1, e2, e3 using Word2Vec or GloVe. We send them into the self-attention block, and we generate dynamic contextual embeddings y1, y2, y3 that understand context.

## 3 - Inventing Self-Attention from First Principles
> ANIM: [manim] Two sentences appear in glowing stylized boxes: "Money bank grows" and "River bank flows". Highlight the word "bank" in both sentences. Morph the representation of Bank into a linear algebraic equation: Bank = alpha * Money + beta * Bank + gamma * Grows with dynamic color-coded coefficients. Then show Bank = alpha * River + beta * Bank + gamma * Flows. Show N-dimensional vector brackets being linearly combined into a new contextual vector.

Now, what is the goal of today's video? We need to understand: What exactly is happening inside this self-attention block? What calculations are being performed that allow us to convert static embeddings into contextual embeddings?

Let's try to understand self-attention from scratch. My belief is that whenever you want to understand something properly, you should approach it from first principles. We will understand self-attention as if we are inventing it for the first time.

We have two sentences: "Money bank grows" and "River bank flows".

Our problem is that the word "bank" is the same word in both sentences, but it is being used in different contexts. In the first sentence, bank relates to money. In the second sentence, bank relates to river. Therefore, the meaning is different.

Unfortunately, if we use ordinary word embeddings, the embedding of bank will remain the same in both sentences.

So let's think about this: What if I don't represent the word simply as "bank"? Instead, I represent bank using the other words around it!

For example: Bank equals some amount of Money plus some amount of Bank plus some amount of Grows. Mathematically: Bank = alpha * Money + beta * Bank + gamma * Grows.

Similarly: Bank = alpha * River + beta * Bank + gamma * Flows.

Now you can immediately see the benefit! The meaning of bank now depends on its context.

What if I represent every word in terms of all the other words in the sentence? For the first sentence "Money Bank Grows", I represent every word using the other words.

There is one small problem: machines don't understand words directly, they use word embeddings. So instead of writing equations using words, we write them using word embeddings: New embedding of Money = alpha * embedding(Money) + beta * embedding(Bank) + gamma * embedding(Grows).

All of these are N-dimensional vectors. When we perform a weighted sum of these vectors, the resulting vector is also N-dimensional.

## 4 - Quantifying Similarity with Dot Products
> ANIM: [manim] An interactive 2D coordinate system appears with vectors v1 = [6, 1], v2 = [4, 2], and v3 = [1, 5]. Draw vector arrows from the origin. Highlight the angle theta between v1 and v2, and between v1 and v3. Show the step-by-step arithmetic: 6*4 + 1*2 = 26 versus 6*1 + 1*5 = 11. Transition to token vectors showing Bank computing dot products with Money, Bank, and Grows to produce raw scores s21, s22, s23.

You may be wondering: What do these numbers actually represent? The numbers represent similarity.

The new embedding is created from old embeddings, and the coefficients tell us how strongly these embeddings are related. So these numbers essentially represent similarity between word embeddings.

How do we calculate similarity between two vectors? One of the simplest ways is the dot product.

If you calculate the dot product between two vectors, it gives you a measure of similarity.

For example, suppose we have three vectors: [6, 1], [4, 2], and [1, 5].

The dot product of the first two vectors is: 6 times 4 plus 1 times 2, which equals 24 plus 2, which equals 26.

Now calculate the dot product of the first and third vectors: 6 times 1 plus 1 times 5, which equals 6 plus 5, which equals 11.

The first and second vectors produce a higher dot product, meaning they are more similar compared to the first and third vectors. Therefore, the dot product gives us a way to quantify similarity!

So the numbers in our equations are essentially dot products between word embeddings.

Let's calculate the new contextual embedding of the word Bank. We calculate its dot product with Money, Bank itself, and Grows. Let's call these scores: s21, s22, and s23.

The first index represents the word whose contextual embedding we are calculating. The second index represents the word we are comparing it with.

So: s21 = Bank dot Money, s22 = Bank dot Bank, and s23 = Bank dot Grows.

## 5 - Softmax Normalization & Contextual Weighted Sum
> ANIM: [manim] Display the raw similarity scores s21, s22, s23. An animated Softmax transformation curve appears with the formula e^(s_i) / sum(e^(s_k)). The raw numbers smoothly transform into normalized probabilities summing to 1.0: w21 = 0.20, w22 = 0.70, w23 = 0.10. An animated weighted combination scales the 3 original embedding vectors and sums them into a glowing resultant vector y_bank.

There is another problem. These raw similarity scores can be very large, very small, or even negative. We want to normalize them so that they become easier to interpret.

Ideally, we want the values to behave like probabilities whose sum is 1. For example: 70% from Bank, 20% from Money, and 10% from Grows. This would be a very clean representation.

To achieve this, we use the Softmax function. We pass our three scores into softmax, and we get weights: w21, w22, and w23, which add up to 1.

The softmax operation calculates: e^(s21) divided by the sum of exponentials for all scores.

Now we have the weights. The next step is to multiply these weights with the corresponding word embeddings: w21 * Money + w22 * Bank + w23 * Grows.

And then we add them together. This gives us the New Bank Embedding, or the Contextual Bank Embedding!

This new embedding is a weighted combination of all three word embeddings. We repeat exactly the same process for Money and Grows.

After doing this for every word, we now have a new contextual embedding for every single word in the sentence!

## 6 - Parallelization with Linear Algebra & Matrices
> ANIM: [manim] Display 3 word embeddings stacking into a 3xN matrix E. Beside it, show the transpose matrix E^T (Nx3). Animate matrix multiplication E * E^T producing a 3x3 score matrix S. Highlight each cell s_ij. Apply row-wise Softmax to get weight matrix W (3x3). Multiply W * E to produce the final contextual embedding matrix Y (3xN). Show GPU compute cores illuminating simultaneously in parallel.

Now let's review this first-principles approach. There is one very important observation.

We calculated the contextual embedding of each word separately. But if you look carefully, these operations don't actually depend on one another.

To calculate Money's contextual embedding, we don't need to first calculate Bank's contextual embedding. Therefore, these operations can be performed completely in parallel!

Even if there are 1,000 words in the sentence, we can calculate their contextual embeddings simultaneously. And this is where linear algebra becomes extremely useful.

Suppose we combine our three word embeddings into one matrix: a 3 by N matrix, where 3 is the number of words and N is the embedding dimension.

Then we multiply this 3 by N matrix with its transpose, which is N by 3. The result is a 3 by 3 matrix containing all our similarity scores s11 through s33.

Now we apply softmax across each row of this entire matrix. This gives us the matrix of attention weights.

Finally, we multiply this weight matrix with the original embedding matrix. The result gives us all the new contextual embeddings at once!

Whether the sentence contains 3 words or 3,000 words, we can perform the operations in parallel using GPUs. Speed and scalability are massive advantages here.

## 7 - The Missing Piece: Learnable Task Context
> ANIM: [manim] Show the current unparameterized pipeline: Dot Product -> Softmax -> Dot Product. Highlight a big warning icon: "No Learnable Weights (W=0)". Display the phrase "This task is a piece of cake." Show literal translation ("cake slice") vs idiomatic translation ("very easy"). Display "Break a leg!" showing literal ("fracture leg") vs idiomatic ("good luck"). Introduce the concept of task-specific training loss and backpropagation.

Now let's consider a major issue with our first-principles self-attention model: it contains no learning parameters!

Whenever you build a deep learning model, you normally have weights and biases so the model can learn from data.

But our current self-attention consists of only fixed dot products and softmax. There are no learnable parameters. That means our contextual embeddings are general rather than task-specific.

Let's understand this with an example. Suppose we want to translate English to Hindi for the sentence: "This task is a piece of cake."

In literal English, "piece of cake" means a slice of cake. But idiomatically, it means "very easy".

Without task-specific learnable parameters, the model might produce a literal translation like "cake ka tukda" instead of "bahut aasan".

Similarly, consider: "Break a leg!" Literally, it means breaking a bone, but as an idiom, it means "Good luck!"

Simply generating general contextual embeddings is not enough. We need task-specific contextual embeddings: optimized for translation, sentiment analysis, or question answering.

We must introduce learnable weights and biases into our self-attention mechanism, so that through backpropagation, the model learns how to create the best contextual embeddings for the task.

## 8 - The Three Roles: Query, Key, and Value
> ANIM: [manim] A word embedding vector for 'Money' splits visually into 3 distinct color-coded icons: a magnifying glass for Query (asks questions), an ID badge for Key (responds with identity), and a content document for Value (carries payload information). Show a Python dictionary animation: D['A'] = 2, where 'A' is the Key, 2 is the Value, and the lookup D[...] is the Query. Connect this directly to token self-attention.

Where do we add learnable weights? We cannot put weights inside softmax, so they must go before or after the similarity calculation.

After carefully examining the process, we realize something profound: every word embedding is actually playing three distinct roles!

They are: Query, Key, and Value.

Let's understand each one.

Query: When we calculate the contextual embedding of Money, Money asks every other embedding: "How similar are you to me?" The vector that asks the question is acting as a Query.

Key: The other embeddings respond to the query. When Money asks Bank, Bank provides the information needed to answer that question. Therefore, these vectors act as Keys. Query asks; Key responds.

Value: After calculating similarity scores and converting them into weights, we perform a weighted sum. The vectors being combined in this final sum are Values. Value is the actual information that gets combined.

This terminology comes from computer science dictionaries: in a Python dictionary D, you query with a key to retrieve its value.

In self-attention, for every word: one embedding acts as Query, other embeddings act as Keys, and their content acts as Values!

## 9 - The Matrimonial Analogy & Separation of Concerns
> ANIM: [manim] A humorous and clear split-screen illustration: A 300-page heavy autobiography book labeled "Original Full Embedding". Three distinct cards branch out from the book: 1. Search Filter ("Query: Looking for professional engineer"), 2. Public Profile ("Key: Bio & Interests"), 3. Personal Conversation ("Value: Deep life stories and character"). Show why uploading the 300-page book directly to every single field fails, illustrating the principle of Separation of Concerns.

Why can't one single vector do all three jobs?

Because of a fundamental principle: separation of concerns. If I force one vector to perform three different jobs, it cannot perform each job optimally. But if we transform the original vector into three specialized vectors, each can excel at its role.

Here is a simple analogy: Imagine an author who wrote a 300-page autobiography containing everything about his life.

Now, at age 35, he registers on a matrimonial website. On this website, there are three main activities:
First: Search - querying for the type of partner he wants.
Second: Profile - a concise summary so others can evaluate compatibility.
Third: Match interaction - sharing meaningful details during conversations.

His 300-page autobiography is like the original word embedding.

The search query is the Query vector.
His profile is the Key vector.
And the meaningful conversation is the Value vector.

If he simply uploaded his entire 300-page book as his profile and search query, nobody would read it. You need crisp, specialized representations.

Similarly, from our single word embedding, we must create three specialized vectors: Query, Key, and Value!

## 10 - Projection Matrices WQ, WK, and WV
> ANIM: [manim] Show an input vector E multiplying with 3 distinct weight matrices: W_Q (Cyan), W_K (Amber), and W_V (Magenta). Show the linear projection equations: Q = E * W_Q, K = E * W_K, V = E * W_V. Animate a neural network training loop: Forward pass -> Loss computation -> Backpropagation gradients -> Updating W_Q, W_K, W_V matrices. Highlight that the exact same W_Q, W_K, W_V are shared across every token.

How do we create Query, Key, and Value from one embedding vector? The answer is linear transformation!

We multiply our original embedding vector by three learnable weight matrices: WQ, WK, and WV.

Therefore:
Q = E times WQ
K = E times WK
V = E times WV

Where do WQ, WK, and WV come from? We don't handcraft them. They start with random weights and are learned automatically during training!

When we pass training examples through the model, we calculate the task loss. Then, backpropagation updates the weights inside WQ, WK, and WV.

Over thousands of iterations, these matrices learn how to project raw embeddings into optimal Query, Key, and Value representations.

And notice something crucial: the exact same WQ, WK, and WV matrices are shared across every word in the sentence! We don't create separate matrices per word; we learn three global projection matrices.

## 11 - The Complete Transformer Attention Mechanism
> ANIM: [manim] A grand finale architectural visualization: Input embeddings matrix E (3xN) multiplied by W_Q, W_K, W_V to form Q, K, V. Compute Q * K^T to get the raw attention score grid. Scale by 1 / sqrt(d_k). Apply Softmax row-wise to create a glowing Attention Weight Heatmap. Multiply by V to output the final dynamic contextual embedding matrix Y. Reveal the iconic formula in glowing gold LaTeX: \text{Attention}(Q, K, V) = \text{Softmax}\left(\frac{Q K^T}{\sqrt{d_k}}\right) V.

Once we have Query, Key, and Value vectors, the entire self-attention mechanism comes together beautifully!

For any word, say Bank:
We take its Query vector Q_bank, compute dot products with all Key vectors K_money, K_bank, and K_grows.
We apply Softmax to get normalized attention weights.
And we compute the weighted sum of all Value vectors V_money, V_bank, and V_grows to produce the final dynamic Contextual Bank Embedding!

In complete matrix form:
Q = E WQ
K = E WK
V = E WV

We compute Q times K transpose, scale by the square root of the key dimension d_k to stabilize gradients, apply Softmax, and multiply by V:

Attention(Q, K, V) = Softmax( Q K transpose / sqrt(d_k) ) times V.

And because this is pure matrix algebra, the entire computation runs in parallel on GPUs, scaling effortlessly from 3 words to thousands of tokens.

From first principles, we have invented the self-attention mechanism that powers the Transformer architecture and modern Generative AI.

I really hope the 14 days of effort behind this explanation gave you true clarity. If you found this valuable, please like and share the video.

Thank you so much for watching, and I will see you in the next one!
