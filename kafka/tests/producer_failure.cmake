execute_process(
    COMMAND "${SIMULATOR}" --output kafka --steps 0
        --bootstrap-servers 127.0.0.1:1 --delivery-timeout-ms 100
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE errors TIMEOUT 8)
if(NOT result STREQUAL "1" OR NOT output MATCHES "event_id" OR
   NOT errors MATCHES "Kafka.*(failed|incomplete|unconfirmed)")
    message(FATAL_ERROR "Failed sends were not surfaced: ${result} ${output} ${errors}")
endif()
