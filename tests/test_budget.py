from core.schemas import StageDSL
from agents.evaluator import StageAwareRouter

router = StageAwareRouter()
stage = StageDSL(
    stage_name="research",
    assigned_model_tier="premium",
    stage_budget=1.0,
    success_criteria={},
    requires_human_approval=False,
    max_retries=3
)
print(router.prepare_routing(stage, "Hello"))
router.update_budget(stage, 0.9)
print(router.prepare_routing(stage, "Hello"))
