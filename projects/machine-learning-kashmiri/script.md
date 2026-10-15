---
title: "Machine Learning in Kashmiri: Complete Intuition & Architecture"
topic: Machine Learning, Supervised Learning, Unsupervised Learning, Reinforcement Learning, Loss Function, Gradient Descent, Overfitting, Generalization
audience: undergraduate computer science & Kashmiri speaking students
aspect: 16:9
language: ks
audio_language: ks
renderer: manim
---

## 1 - مشین لرننگ کیا چھُ؟ (What is Machine Learning?)
> ANIM: Split comparison between Traditional Programming (Rules + Data = Output) and Machine Learning (Data + Answers = Learned Model)

سلام! اَز ہؠچھَو اَسؠ کہ مشین لرننگ کیا چھُ تہٕ یہِ کِتھ پٲٹھؠ چھُ کٲم کران۔ روایتی پروگرامنگ مَنٛز چھُ اِنسان کمپیوٹرس واضح قواعد تہٕ ڈیٹا دِوان، یمہِ سٟتؠ جواب حٲصل گژھان چھُ۔ مگر مشین لرننگ مَنٛز چھُ کمپیوٹر ڈیٹا تہٕ جواباتن ہٕنٛدِ مشاہدٕ سٟتؠ خود بخود قواعِد تلاش کران۔ اَمی کِنؠ چھِ کمپیوٹر وقتَس سٟتؠ سٟتؠ پانہِ سؠکھان تہٕ نٔون مسائلن ہُنٛد حل کڈان۔

## 2 - مشین لرننگ ہٕنٛدی ترٛے قسٕم (Three Paradigms of Machine Learning)
> ANIM: Three cards displaying Supervised Learning (labeled pairs), Unsupervised Learning (clustering), and Reinforcement Learning (reward loop)

مشین لرننگ چھِ بُنیادی طور ترٛؠن اہم قِسمَن مَنٛز تقسیٖم گژھان۔ گوڈنیک چھُ سُوپر وائزڈ لرننگ، یَتھ مَنٛز ماڈلس لیبلڈ ڈیٹا دِنہٕ چھُ یِوان، مِثال کے طور پٲٹھؠ قیمتن ہُنٛد اندازٕ لگاوُن یا امیج کلاسیفیکیشن۔ دویم چھُ اَن سُوپر وائزڈ لرننگ، یَتھ مَنٛز کمپیوٹر بغیر کانہہ لیبل ڈیٹا مَنٛز چھُپیومٕتؠ پیٹرن تہٕ کلسٹرس لَبھان۔ تہٕ ترٛیم چھُ ری اِنفورسمنٹ لرننگ، یَتھ مَنٛز اَکھ ایجنٹ ماحولَس مَنٛز اِنعام تہٕ سزایہِ سٟتؠ سؠکھان چھُ۔

## 3 - ماڈل کِتھ پٲٹھؠ چھُ سؠکھان؟ لاس فنکشن تہٕ گریڈینٹ ڈیسینٹ (How Models Learn)
> ANIM: Convex Loss parabola J(w) with tangent gradient slope and optimizer ball stepping iteratively down to minimum error

ماڈل کِتھ پٲٹھؠ چھُ سؠکھان؟ اَتھ عملہِ مَنٛز چھُ لاس فَنکشن تہٕ گریڈینٹ ڈیسینٹ سارِوٕے کھۄتہٕ اہم کردار ادا کران۔ ماڈل چھُ اَکھ پیش گوئی کران، تہٕ لاس فنکشن چھُ یہِ ناپان زِ ماڈلٕک جواب تہٕ اصل جوابس مَنٛز کِتیا غَلطی یا فرق چھُ۔ اَمہِ پتہٕ چھُ کمپیوٹر گریڈینٹ ڈیسینٹ زریعہٕ ماڈلٕک پیرامیٹرز یعنی ویٹس ایڈجسٹ کران۔ ہر قدمَس سٟتؠ چھِ غلطی کم گژھان، ییتھ کٔنؠ اَکھ بال پھیران ڈھلوان پؠٹھٕ بۄن یِوان تہٕ کم ترین مقامَس پؠٹھ رُکان۔

## 4 - اوورفِٹِنٛگ بمقابلہ انڈرفِٹِنٛگ (Overfitting vs Underfitting)
> ANIM: Three regression subplots comparing high bias underfitting, balanced generalization, and high variance overfitting

ماڈل ٹریننگ دوران چھِ زٕ اَہَم مَسلہٕ پیش یِوان: اَنڈرفِٹِنٛگ تہٕ اوورفِٹِنٛگ۔ انڈرفٹنگ تِلہِ چھُ گژھان ییلہِ ماڈل سؠٹھا سادہ آسہِ تہٕ ڈیٹا ہُنٛد بنیادی نمونہٕ سمجھی نہِ، یَتھ ہائی بائس ونان چھِ۔ اوورفٹنگ تِلہِ چھُ گژھان ییلہِ ماڈل ڈیٹا ہٕنٛز سارِوٕے آواز تہٕ شور رٹہٕ مارِ، تہٕ نٔوس ڈیٹا ہَس پؠٹھ ناکام گژھِ، یَتھ ہائی ویرینس ونان چھِ۔ اَمہِ موجوب چھُ سانین مقصد اَکھ متوازن ماڈل بناوُن یُس اصل طریقہٕ سٟتؠ جنرلائز کٔرِ۔

## 5 - اصل دُنیاہَس مَنٛز استعمال تہٕ خلاصہٕ (Real-World Applications & Summary)
> ANIM: Showcase grid of real-world AI applications including Medical Imaging, Kashmiri Language AI, Autonomous Vehicles, and Summary Badges

مشین لرننگ ہُنٛد اِستعمال چھُ اَز کل سانہِ روزمرہ زندگی مَنٛز ہر شعبس مَنٛز گژھان۔ صحت عامہ مَنٛز ایکسرے تہٕ ایم آر آئی اسکینن ہٕنٛز جانچ، خود مختار گاڑؠن ہٕنٛز ڈرائیونگ، تہٕ کٲشِرِ زَبانہِ ہُنٛد خودکار ترجمہٕ کرُن اَمیک بہترین مثال چھِ۔ مشین لرننگ چھِ دُنیاہَس بدلاوان، تہٕ یہِ سؠکھُن چھُ مستقبل ہٕنٛدِ خٲطرٕ اَکھ لاجواب صلاحیت۔ اَتھ ویڈیو ہَس مَنٛز شٲمل گژھنہٕ خٲطرٕ بٔڑؠ مہربٲنی، شُکریہ!
