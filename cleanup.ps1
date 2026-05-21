# cleanup.ps1
Write-Host "Cleaning up old assignment containers..."

# Remove exited containers
docker ps -a --filter "name=assignment_" --filter "status=exited" -q | ForEach-Object {
    Write-Host "Removing $_"
    docker rm -f $_
}

# Optional: Remove co
# docker ps -a --filter "name=assignment_" -q | ForEach-Object {
#     docker rm -f $_
# }

Write-Host "✅ Cleanup complete!"
Write-Host ""
docker ps -a --filter "name=assignment_"