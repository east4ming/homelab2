#!/bin/bash

# 定义源目录
source_dir="."

# 遍历 rsshub 下的所有子目录
for subdir in "$source_dir"/*/; do
    # 获取子目录名（去掉路径和末尾的斜杠）
    subdir_name=$(basename "$subdir")

    # 遍历子目录中的所有文件
    for file in "$subdir"*; do
        # 获取文件名（去掉路径）
        filename=$(basename "$file")

        # 检查是否是文件（排除目录）
        if [ -f "$file" ]; then
            # 定义新文件名
            new_filename="${subdir_name}-${filename}"

            # 移动并重命名文件
            mv "$file" "${source_dir}/${new_filename}"
            echo "Moved: $file -> ${source_dir}/${new_filename}"
        fi
    done
done
