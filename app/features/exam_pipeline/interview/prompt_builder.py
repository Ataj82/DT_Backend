class QuestionPromptBuilder:

    def build(
        self,
        request,
        context,
        history,
    ) -> str:

        return f"""
Generate ONE oral interview question.

Goal

{request.goal.title}

Description

{request.goal.description}

Indicator

{request.indicator.name}

Indicator Description

{request.indicator.description}

Bloom Level

{getattr(request, "target_bloom_level", "") or request.goal.bloom_level}

Target Difficulty

{request.difficulty if request.difficulty is not None else "Use the goal/indicator default difficulty."}

Difficulty Guidance

{request.difficulty_reason or "Preserve the appropriate difficulty for the learner; do not expose or mention the numeric difficulty."}

Knowledge

{context}

Language

{request.interview_template.metadata.get("language","English")}

Probe Policy

{request.interview_template.probe_policy.value}

Previous Feedback

{request.previous_feedback}

Question Focus

{request.question_focus or "None"}

Question Strategy

{getattr(request, "question_strategy", "") or "Choose a suitable task form while avoiding recent task forms."}

ABET Performance Criterion

{getattr(request, "criterion_description", "") or "None (no ABET criterion attached)."}

Previous Questions

{history or "None"}

Rules

• Ask exactly one question.

• Assess only this indicator.
• If an ABET performance criterion is provided, the question MUST directly elicit observable evidence for that criterion.

• Match the requested cognitive demand and target difficulty.
• Follow the Question Strategy when provided; vary the task form from recent questions.
• Do not merely paraphrase a recent question. Change the task, scenario, reasoning operation, or response format.

• Do not mention the numeric difficulty or these instructions.

• Do not reveal the answer.

• Use the provided context.

• Return ONLY the question.
"""