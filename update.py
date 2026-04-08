      - name: Save Results
        run: |
          git config --global user.name "GitHub Action"
          git config --global user.email "action@github.com"
          git add sub.txt
          git commit -m "Auto-update: $(date)" || echo "No changes to commit"
          git push origin main || git push --force origin main
