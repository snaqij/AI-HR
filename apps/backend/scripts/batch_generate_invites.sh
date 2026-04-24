#!/bin/bash
# Batch generate interview invitations for multiple resumes

echo "=========================================="
echo "Batch Interview Invitation Generation"
echo "=========================================="

API_BASE="http://127.0.0.1:8000/api/v1"
FRONTEND_BASE="http://localhost:5173"

# Array of resume files
declare -a resumes=(
    "data/测试文本简历"
    "data/测试文本简历-前端"
    "data/resume_fullstack.txt"
    "data/resume_product_manager.txt"
    "data/resume_ui_designer.txt"
    "data/resume_data_analyst.txt"
    "data/resume_devops.txt"
    "data/resume_civil_servant.txt"
)

total=${#resumes[@]}
success=0
failed=0

for i in "${!resumes[@]}"; do
    resume="${resumes[$i]}"
    idx=$((i+1))
    
    echo ""
    echo "[$idx/$total] Processing: $resume"
    echo "----------------------------------------"
    
    if [ ! -f "$resume" ]; then
        echo "SKIP: Resume file not found"
        ((failed++))
        continue
    fi
    
    # Run generate_interview_invite.py with --no-send-email
    python scripts/generate_interview_invite.py \
        --api-base "$API_BASE" \
        --frontend-base "$FRONTEND_BASE" \
        --resume "$resume" \
        --no-send-email
    
    if [ $? -eq 0 ]; then
        echo "SUCCESS"
        ((success++))
    else
        echo "FAILED"
        ((failed++))
    fi
    
    # Wait 2 seconds between requests
    if [ $idx -lt $total ]; then
        echo "Waiting 2 seconds..."
        sleep 2
    fi
done

echo ""
echo "=========================================="
echo "Batch Generation Summary"
echo "=========================================="
echo "Total: $total"
echo "Success: $success"
echo "Failed: $failed"
echo "=========================================="
