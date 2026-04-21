from vidur.config import (
    RandomForrestExecutionTimePredictorConfig,
    ReplicaConfig,
    SarathiSchedulerConfig,
)
from vidur.entities.execution_time import ExecutionTime


def _build_execution_time(profiling_time_unit: str) -> ExecutionTime:
    predictor_config = RandomForrestExecutionTimePredictorConfig(
        profiling_time_unit=profiling_time_unit
    )
    replica_config = ReplicaConfig()
    scheduler_config = SarathiSchedulerConfig()

    # Keep one block at 1000 "profiling units" exactly:
    # attention=1 + mlp=1 + add=998
    return ExecutionTime(
        num_layers_per_pipeline_stage=1,
        attention_rope_execution_time=0.0,
        attention_kv_cache_save_execution_time=0.0,
        attention_decode_execution_time=1.0,
        attention_prefill_execution_time=0.0,
        attention_layer_pre_proj_execution_time=0.0,
        attention_layer_post_proj_execution_time=0.0,
        mlp_layer_up_proj_execution_time=1.0,
        mlp_layer_down_proj_execution_time=0.0,
        mlp_layer_act_execution_time=0.0,
        attn_norm_time=0.0,
        mlp_norm_time=0.0,
        add_time=998.0,
        tensor_parallel_communication_time=0.0,
        pipeline_parallel_communication_time=0.0,
        schedule_time=0.0,
        sampler_e2e_time=0.0,
        prepare_inputs_e2e_time=0.0,
        process_model_outputs_time=0.0,
        ray_comm_time=0.0,
        predictor_config=predictor_config,
        replica_config=replica_config,
        replica_scheduler_config=scheduler_config,
    )


def test_model_time_uses_milliseconds_by_default():
    execution_time = _build_execution_time("ms")
    assert execution_time.model_time == 1.0


def test_model_time_supports_microseconds():
    execution_time = _build_execution_time("us")
    assert execution_time.model_time == 0.001
