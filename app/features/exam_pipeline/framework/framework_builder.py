"""
Application composition root.

Constructs application-wide services and collaborators.
"""

from __future__ import annotations

from ..language.evaluator import LanguageAwareAnswerEvaluator
from ..language.question_prompt_router import LanguageAwareQuestionPromptBuilder
from ..framework.assessment_framework import (
    AssessmentFramework,
)

from ..framework.framework_services import (
    FrameworkServices,
)

# ==========================================================
# Repositories
# ==========================================================

from ..repositories.memory.memory_knowledge_repository import (
    MemoryKnowledgeRepository,
)

from ..repositories.memory.memory_goal_repository import (
    MemoryGoalRepository,
)

from ..repositories.memory.memory_session_repository import (
    MemorySessionRepository,
)

# ==========================================================
# Unit Of Work
# ==========================================================

from ..unit_of_work.memory_unit_of_work import (
    MemoryUnitOfWork,
)

# ==========================================================
# Assessment
# ==========================================================

from ..assessment.coverage_engine import (
    CoverageEngine,
)

from ..assessment.difficulty import (
    AdaptiveDifficultyController,
)

from ..assessment.information_gain import (
    InformationGainPlanner,
)

from ..assessment.evidence_planner import (
    EvidencePlanner,
)

from ..assessment.outcome_manager import (
    OutcomeManager,
)

from ..assessment.progress_reasoner import (
    ProgressReasoner,
)

from ..assessment.engine import (
    AssessmentEngine,
)

from ..assessment.evaluation.evaluation_service import (
    EvaluationService,
)

from ..assessment.evaluation.answer_evaluator import (
    AnswerEvaluator,
)

from ..assessment.result_builder import (
    AssessmentResultBuilder,
)

from ..assessment.context_factory import (
    AssessmentContextFactory,
)

from ..abet.service import ABETService

from ..assessment.runtime_factory import (
    AssessmentRuntimeFactory,
)

# ==========================================================
# Interview
# ==========================================================

from ..interview.question_generator import (
    QuestionGenerator,
)

from ..interview.prompt_builder import (
    QuestionPromptBuilder,
)

from ..interview.knowledge_retriever import (
    KnowledgeRetriever,
)

# ==========================================================
# LLM
# ==========================================================

from ..llm.provider import (
    LLMProvider,
)

from ..configuration.llm_configuration import (
    LLMConfiguration,
)

# ==========================================================
# Application Services
# ==========================================================

from ..services.knowledge_service import (
    KnowledgeService,
)

from ..services.goal_service import (
    GoalService,
)

from ..services.interview_service import (
    InterviewService,
)

from ..services.assessment_service import (
    AssessmentService,
)
from ..multiuser.service import MultiUserService

# ==========================================================
# Reporting
# ==========================================================

from ..reports.metrics_service import (
    MetricsService,
)

from ..reports.report_service import (
    ReportService,
)

from ..reports.research_report_generator import (
    ResearchReportGenerator,
)

# ==========================================================
# Knowledge
# ==========================================================

from ..knowledge.processor import (
    KnowledgeProcessor,
)

from ..knowledge.provider import (
    KnowledgeProvider,
)


class FrameworkBuilder:
    """
    Application composition root.

    Production:

        FrameworkBuilder().build()

    Tests:

        FrameworkBuilder(
            configuration=...,
            llm=fake_llm,
        ).build()

    The builder owns dependency wiring only.
    """

    def __init__(
        self,
        *,
        configuration=None,
        llm=None,
    ) -> None:
        self.configuration = configuration
        self.llm = llm

    def build(
        self,
    ) -> AssessmentFramework:

        # ======================================================
        # Repositories
        # ======================================================

        knowledge_repository = (
            MemoryKnowledgeRepository()
        )

        goal_repository = (
            MemoryGoalRepository()
        )

        session_repository = (
            MemorySessionRepository()
        )

        # ======================================================
        # Unit Of Work
        # ======================================================

        unit_of_work = MemoryUnitOfWork(
            knowledge_repository=(
                knowledge_repository
            ),
            goal_repository=(
                goal_repository
            ),
            session_repository=(
                session_repository
            ),
        )

        # ======================================================
        # Knowledge Pipeline
        # ======================================================

        knowledge_provider = (
            KnowledgeProvider()
        )

        knowledge_processor = (
            KnowledgeProcessor()
        )

        # ======================================================
        # Assessment Algorithms
        # ======================================================

        coverage_engine = (
            CoverageEngine()
        )

        difficulty_controller = AdaptiveDifficultyController()

        information_gain_planner = (
            InformationGainPlanner()
        )

        evidence_planner = EvidencePlanner(
            information_gain_planner=(
                information_gain_planner
            ),
        )

        outcome_manager = OutcomeManager(
            coverage_engine=(
                coverage_engine
            ),
        )

        progress_reasoner = ProgressReasoner(
            coverage_engine=(
                coverage_engine
            ),
            evidence_planner=(
                evidence_planner
            ),
        )

        # ======================================================
        # LLM
        # ======================================================
        #
        # IMPORTANT:
        #
        # Build the LLM BEFORE constructing AnswerEvaluator.
        #
        # Otherwise:
        #
        #     AnswerEvaluator(llm=llm)
        #
        # references a local variable that does not yet exist.
        # ======================================================

        llm = self._build_llm()

        # ======================================================
        # Answer Evaluation
        # ======================================================
        #
        # P0:
        #
        # AnswerEvaluator is now the semantic evaluation boundary.
        #
        # It receives the same LLM instance used by the
        # question-generation pipeline.
        # ======================================================

        answer_evaluator = LanguageAwareAnswerEvaluator(
            llm=llm,
        )

        evaluation_service = EvaluationService(
            evaluator=answer_evaluator,
            outcome_manager=outcome_manager,
            progress_reasoner=progress_reasoner,
            coverage_engine=coverage_engine,
        )

        assessment_engine = AssessmentEngine(
            evaluation_service=(
                evaluation_service
            ),
        )

        # ======================================================
        # Knowledge Retriever
        # ======================================================
        #
        # Current KnowledgeRetriever expects:
        #
        #     repository.retrieve(indicator)
        #
        # MemoryKnowledgeRepository exposes search().
        #
        # This adapter bridges that interface.
        #
        # Knowledge-base isolation remains a later task.
        # ======================================================

        class _KnowledgeRepositoryAdapter:
            """
            Compatibility adapter for KnowledgeRetriever.
            """

            def __init__(
                self,
                repository,
            ) -> None:
                self.repository = repository

            def retrieve(
                self,
                indicator,
                *,
                knowledge_model=None,
                language=None,
            ) -> str:
                """Retrieve only from the active interview knowledge snapshot.

                The previous implementation searched every repository knowledge
                base, which allowed unrelated/Persian material to enter an
                English interview. The session snapshot is now the primary
                scope. English retrieval also rejects Persian/Arabic-script
                source passages rather than exposing them to the generator.
                """
                query = (
                    getattr(indicator, "description", None)
                    or getattr(indicator, "name", None)
                    or str(indicator)
                )

                if knowledge_model is not None:
                    knowledge_id = getattr(knowledge_model, "id", None)
                    if knowledge_id:
                        results = self.repository.search(
                            knowledge_id=str(knowledge_id),
                            query=query,
                            top_k=5,
                        )
                    else:
                        results = []
                else:
                    # Compatibility fallback for legacy callers that do not
                    # carry a session knowledge snapshot.
                    results = []
                    for kb in self.repository.list():
                        results.extend(
                            self.repository.search(
                                knowledge_id=kb.id,
                                query=query,
                                top_k=3,
                            )
                        )

                parts: list[str] = []
                normalized_language = str(language or "en").strip().lower()
                for result in results:
                    if isinstance(result, dict):
                        text = result.get("text")
                        metadata = result.get("metadata") or {}
                    else:
                        text = str(result)
                        metadata = {}

                    if not text:
                        continue

                    if normalized_language == "en":
                        explicit = str(metadata.get("language") or "").strip().lower()
                        if explicit in {"fa", "fas", "per", "persian", "farsi", "فارسی"}:
                            continue
                        # When document metadata is absent, prevent Persian/Arabic
                        # script from crossing the English interview boundary.
                        if any("\u0600" <= ch <= "\u06ff" for ch in str(text)):
                            continue

                    parts.append(str(text))

                if parts:
                    return "\n\n".join(parts)
                if normalized_language == "en":
                    return "No English-compatible knowledge context is available."
                return query

        knowledge_retriever = KnowledgeRetriever(
            knowledge_repository=(
                _KnowledgeRepositoryAdapter(
                    knowledge_repository
                )
            ),
        )

        # ======================================================
        # Question Generation
        # ======================================================

        prompt_builder = LanguageAwareQuestionPromptBuilder(
            english=QuestionPromptBuilder(),
        )

        question_generator = QuestionGenerator(
            llm=llm,
            knowledge_retriever=(
                knowledge_retriever
            ),
            prompt_builder=(
                prompt_builder
            ),
        )

        # ======================================================
        # Result Builder
        # ======================================================

        result_builder = (
            AssessmentResultBuilder()
        )

        # ======================================================
        # Runtime Factories
        # ======================================================

        abet_service = ABETService()

        context_factory = AssessmentContextFactory(
            coverage_engine=(
                coverage_engine
            ),
            evidence_planner=(
                evidence_planner
            ),
            progress_reasoner=(
                progress_reasoner
            ),
            question_generator=(
                question_generator
            ),
            result_builder=(
                result_builder
            ),
            abet_service=abet_service,
        )

        runtime_factory = AssessmentRuntimeFactory(
            context_factory=(
                context_factory
            ),
            result_builder=(
                result_builder
            ),
            evaluation_service=(
                evaluation_service
            ),
            difficulty_controller=(
                difficulty_controller
            ),
            abet_service=abet_service,
        )

        # ======================================================
        # Application Services
        # ======================================================

        knowledge_service = KnowledgeService(
            provider=knowledge_provider,
            processor=knowledge_processor,
            uow=unit_of_work,
        )

        goal_service = GoalService(
            uow=unit_of_work,
        )

        interview_service = InterviewService(
            runtime_factory=(
                runtime_factory
            ),
            uow=unit_of_work,
        )

        assessment_service = AssessmentService(
            runtime_factory=(
                runtime_factory
            ),
            uow=unit_of_work,
        )

        # ======================================================
        # Reporting
        # ======================================================

        metrics_service = (
            MetricsService()
        )

        report_service = ReportService(
            generator=(
                ResearchReportGenerator()
            ),
            metrics_service=(
                metrics_service
            ),
        )

        # ======================================================
        # Multi-user assignment layer
        # ======================================================
        # This layer sits above InterviewService and never participates in
        # question generation, evaluation, scoring, navigation, or mastery.
        multi_user_service = MultiUserService(
            interview_service=interview_service,
            knowledge_service=knowledge_service,
            goal_service=goal_service,
        )

        # ======================================================
        # Framework
        # ======================================================

        services = FrameworkServices(
            knowledge_service=(
                knowledge_service
            ),
            goal_service=(
                goal_service
            ),
            interview_service=(
                interview_service
            ),
            assessment_service=(
                assessment_service
            ),
            report_service=(
                report_service
            ),
            abet_service=abet_service,
            multi_user_service=multi_user_service,
        )

        return AssessmentFramework(
            services=services
        )

    # ==========================================================
    # LLM Construction
    # ==========================================================

    def _build_llm(self):
        """
        Resolve the LLM dependency.

        Priority:

        1. Explicitly injected provider.
        2. Configuration object's LLM configuration.
        3. Environment-backed LLMConfiguration.
        """

        if self.llm is not None:
            return self.llm

        llm_configuration = getattr(
            self.configuration,
            "llm",
            None,
        )

        if llm_configuration is None:
            llm_configuration = (
                LLMConfiguration.from_env()
            )

        return LLMProvider(
            configuration=llm_configuration,
        )