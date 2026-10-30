---
title: LLM Evaluations
topic: benchmark datasets, human evaluation, automated LLM-as-a-judge, BLEU and ROUGE metrics, data contamination and memorization, alignment testing
audience: undergraduate computer science
aspect: 16:9
language: en
---

<!-- HOW THIS FILE WORKS
     Each "## N - Title" block is one section.
     The "> ANIM:" line is the brief `prompt2render scenes` storyboards against scenekit.
     Everything else is what YOU say. Write it in your own voice.

     Aim ~140 spoken words per minute; ~5 min total = ~700 words
     across 4 section(s). This outline was AI-suggested -- add, remove or rename sections freely,
     and every section still needs real narration before you build.
-->

## 1 - Why Vibe Checks Fail
> ANIM: Show a developer casually chatting with an LLM and getting a clever response, followed by a sudden catastrophic failure in production, and then overlay text stating the learning objective of exploring the engineering principles behind rigorous evaluation.

How do we actually know if a large language model is truly ready for real world software deployment? Today, we will explore the engineering principles behind rigorous language model evaluation, moving from static datasets to automated judges. When you chat with a model during development, it often provides clever and engaging responses to simple prompts. You might be tempted to ship that model based entirely on a few casual interactions. But conversational testing hides catastrophic failures that only appear later when real users push the system in complex production environments. Relying on subjective impressions leaves your application vulnerable to unexpected errors, hallucinations, and unpredictable behavior. To build reliable software, we need systematic evaluation methods that measure true capability rather than superficial charm.

## 2 - Static Datasets and Accuracy
> ANIM: Display a block diagram of a pipeline feeding multiple-choice questions from benchmarks like MMLU and GSM8K into a model to compute a deterministic accuracy percentage.

The first major step toward rigorous testing is using static benchmark datasets. These datasets provide standardized collections of problems with explicitly known correct answers. Prompts, such as multiple choice questions from massive benchmarks like MMLU or grade school math problems from GSM8K, are fed directly into the model through an automated pipeline. The system then evaluates the model output against the ground truth to compute a precise, deterministic accuracy percentage. This gives developers a clear baseline score, allowing you to track whether model updates improve performance or degrade it over successive iterations. However, static multiple choice tests do not fully capture open ended generation, creative expression, or complex multi step reasoning, which requires more advanced testing strategies.

## 3 - LLM-as-a-Judge and Elo
> ANIM: Display a prompt on screen, followed by two side by side model responses. An arrow points from both responses to a referee model block that outputs a win verdict for model A, and a dashboard animates an upward tick in model A's Elo rating.

To evaluate open ended text where exact string matches fail, we turn to automated evaluation using stronger models, functioning as an automated judge. Consider a prompt asking the model to explain recursion. Model A gives a clear programming example, while Model B provides a vague circular definition. Both responses go simultaneously to a more capable referee language model. The referee reviews both and issues a pairwise preference verdict, declaring Model A the winner. These win and loss outcomes feed directly into a live leaderboard that calculates dynamic Elo ratings for each competing model. This approach correlates well with human evaluation preferences while scaling efficiently across thousands of generations.

## 4 - Contamination and What Next
> ANIM: Visualize a training data corpus overlapping heavily with a benchmark test set as a Venn diagram, then transition to a summary graphic displaying three pillars: static baselines, automated judges, and contamination awareness.

Even with robust leaderboards and static datasets, modern evaluation faces a severe threat known as data contamination and memorization. When a model training corpus overlaps heavily with a benchmark test set, the model effectively memorizes the exact answers instead of learning how to reason logically. High test scores can become completely misleading if the evaluation data accidentally leaked into the pretraining phase without our knowledge. Detecting this memorization and testing true generalization remain major hurdles in machine learning research. To build trustworthy systems, our overall evaluation strategy must combine all three pillars we have covered: static baselines for deterministic tracking, automated judges for open ended scaling, and rigorous contamination awareness to verify true generalization.

