"""Arabic-only question-generation prompt."""
from __future__ import annotations


class ArabicQuestionPromptBuilder:
    def build(self, request, context, history) -> str:
        intro_directive = (
            getattr(request, 'system_prompt_override', None)
            or getattr(request, 'prompt_directive', None)
            or "أنت محاور تعليمي أكاديمي محترف وناطق باللغة العربية الفصحى. قم بصياغة سؤال شفاهي واحد فقط، دقيق، واضح، وطبيعي لطالب جامعي."
        )
        return f"""
{intro_directive}


هدف التعلم:
{request.goal.title}

وصف الهدف:
{request.goal.description}

مؤشر التقييم:
{request.indicator.name}

وصف المؤشر:
{request.indicator.description}

مستوى بلوم المستهدف:
{getattr(request, 'target_bloom_level', '') or request.goal.bloom_level}

مستوى الصعوبة المستهدف:
{request.difficulty if request.difficulty is not None else 'استخدم مستوى الصعوبة الافتراضي للهدف/المؤشر.'}

توجيه الصعوبة:
{request.difficulty_reason or 'حافظ على مستوى صعوبة مناسب للمتعلم دون ذكر القيمة الرقمية للصعوبة.'}

المعرفة والسياق التعليمي المرتبط:
{context}

سياسة أسئلة المتابعة:
{request.interview_template.probe_policy.value}

التغذية الراجعة السابقة:
{request.previous_feedback}

تركيز السؤال:
{request.question_focus or 'غير محدد'}

استراتيجية السؤال:
{getattr(request, 'question_strategy', '') or 'اختر نمط سؤال مناسب ولا تكرر نمط الأسئلة السابقة.'}

معيار أداء ABET:
{getattr(request, 'criterion_description', '') or 'غير محدد'}

الأسئلة السابقة:
{history or 'لا توجد أسئلة سابقة'}

قواعد التوليد:
- قم بتوليد سؤال شفاهي واحد فقط.
- وجه السؤال مباشرة إلى الطالب؛ لا تكتبه على هيئة تعليق أو شرح عن السؤال.
- يجب أن يكون السؤال باللغة العربية الفصحى السليمة والسلسة، وليس ترجمة حرفية من الإنجليزية.
- استخدم التعبيرات والمصطلحات الدقيقة باللغة العربية مع الحفاظ على المصطلحات التقنية والبرمجية بالإنجليزية عند اللزوم (مثل الكلمة المفتاحية def في بايثون).
- يجب أن يقيس السؤال هذا المؤشر التعليمي المحدد فقط.
- التزم بالمستوى المعرفي (بلوم) ومستوى الصعوبة المطلوبين.
- اعتمد حصراً على المعرفة والسياق المتاح ولا تبتدع معلومات غير متوفرة.
""".strip()
