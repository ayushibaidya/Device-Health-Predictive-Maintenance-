if(NOT DEFINED SIMULATOR OR NOT DEFINED VALIDATOR OR NOT DEFINED OUTPUT_DIR)
    message(FATAL_ERROR "SIMULATOR, VALIDATOR, and OUTPUT_DIR are required")
endif()
if(NOT DEFINED MODE)
    set(MODE default)
endif()

file(MAKE_DIRECTORY "${OUTPUT_DIR}")
if(MODE STREQUAL "reset")
    set(arguments --steps 705 --reset-at-step 700)
else()
    set(arguments --steps 1200)
endif()

foreach(run IN ITEMS first second)
    execute_process(
        COMMAND "${SIMULATOR}" ${arguments}
        RESULT_VARIABLE result
        OUTPUT_FILE "${OUTPUT_DIR}/${run}.jsonl"
        ERROR_VARIABLE errors
        TIMEOUT 10)
    if(NOT result STREQUAL "0" OR NOT errors STREQUAL "")
        message(FATAL_ERROR "Simulator failed: ${result} ${errors}")
    endif()
endforeach()
file(SHA256 "${OUTPUT_DIR}/first.jsonl" first_hash)
file(SHA256 "${OUTPUT_DIR}/second.jsonl" second_hash)
if(NOT first_hash STREQUAL second_hash)
    message(FATAL_ERROR "Identical CLI inputs did not produce identical bytes")
endif()

execute_process(
    COMMAND "${VALIDATOR}" "${OUTPUT_DIR}/first.jsonl" "${MODE}"
    RESULT_VARIABLE result
    OUTPUT_VARIABLE report
    ERROR_VARIABLE errors
    TIMEOUT 10)
if(NOT result STREQUAL "0")
    message(FATAL_ERROR "Output validation failed: ${result} ${errors}")
endif()
message("${report}Output SHA256: ${first_hash}\nDemo data: ${OUTPUT_DIR}/first.jsonl")
