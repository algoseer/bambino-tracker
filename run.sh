docker run --rm -d \
    --name kalki-logs \
    -v $PWD:/app \
    -p 3030:8501 \
    --privileged \
    baby-tracker:latest