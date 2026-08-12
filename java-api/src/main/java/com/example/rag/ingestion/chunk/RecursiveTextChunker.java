package com.example.rag.ingestion.chunk;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

/**
 * 递归切分器。
 *
 * <p>修复点：切分时保留分隔符（标点/换行不丢失），
 * 并为每个片段记录原文近似偏移，不再输出 -1。</p>
 */
@Component
@RequiredArgsConstructor
public class RecursiveTextChunker implements TextChunker {

    private final FixedSizeTextChunker fixedSizeTextChunker;

    /**
     * 从大结构到小结构依次尝试切分。
     */
    private static final String[] SEPARATORS = {
            "\n\n", "\n", "。", "！", "？", ".", "!", "?", "；", ";", "，", ",", " "
    };

    /**
     * 携带原文偏移的片段；分隔符保留在 content 尾部。
     */
    private record Piece(String content, int start, int end) {
    }

    @Override
    public List<TextChunk> chunk(String text, int chunkSize, int overlap) {
        if (text == null || text.isBlank()) {
            return List.of();
        }

        // 先递归拆成带偏移的小片段（分隔符保留）。
        List<Piece> pieces = splitRecursive(text.trim(), chunkSize, 0);

        // 再合并成目标大小的 Chunk。
        return mergePieces(pieces, chunkSize, overlap, text.length());
    }

    private List<Piece> splitRecursive(
            String text,
            int chunkSize,
            int separatorIndex
    ) {
        if (text.length() <= chunkSize) {
            return List.of(new Piece(text, 0, text.length()));
        }

        if (separatorIndex >= SEPARATORS.length) {
            // 无更多分隔符：降级固定长度切分，保留偏移。
            return fixedSizeTextChunker
                    .chunk(text, chunkSize, 0)
                    .stream()
                    .map(chunk -> new Piece(
                            chunk.getContent(),
                            chunk.getStartOffset(),
                            chunk.getEndOffset()
                    ))
                    .toList();
        }

        String separator = SEPARATORS[separatorIndex];
        List<Piece> result = new ArrayList<>();
        boolean found = false;
        int pos = 0;
        int idx;

        while ((idx = text.indexOf(separator, pos)) != -1) {
            int partEnd = idx + separator.length();
            String part = text.substring(pos, partEnd);
            String clean = part.trim();

            if (!clean.isBlank()) {
                found = true;
                // 计算 trim 后的精确偏移。
                int leading = part.length() - part.stripLeading().length();
                int trailing = part.length() - part.stripTrailing().length();
                int cleanStart = pos + leading;
                int cleanEnd = partEnd - trailing;

                if (clean.length() > chunkSize) {
                    // 片段仍超长：递归到下一级分隔符，偏移整体平移。
                    for (Piece sub : splitRecursive(
                            clean, chunkSize, separatorIndex + 1
                    )) {
                        result.add(new Piece(
                                sub.content(),
                                cleanStart + sub.start(),
                                cleanStart + sub.end()
                        ));
                    }
                } else {
                    result.add(new Piece(clean, cleanStart, cleanEnd));
                }
            }
            pos = partEnd;
        }

        // 最后一段（后面没有分隔符）。
        if (pos < text.length()) {
            String tail = text.substring(pos);
            String cleanTail = tail.trim();
            if (!cleanTail.isBlank()) {
                found = true;
                int leading = tail.length() - tail.stripLeading().length();
                int cleanStart = pos + leading;
                int cleanEnd = text.length() - (
                        tail.length() - tail.stripTrailing().length()
                );

                if (cleanTail.length() > chunkSize) {
                    for (Piece sub : splitRecursive(
                            cleanTail, chunkSize, separatorIndex + 1
                    )) {
                        result.add(new Piece(
                                sub.content(),
                                cleanStart + sub.start(),
                                cleanStart + sub.end()
                        ));
                    }
                } else {
                    result.add(new Piece(
                            cleanTail, cleanStart, cleanEnd
                    ));
                }
            }
        }

        if (!found) {
            // 当前分隔符未命中任何非空片段：尝试下一级。
            return splitRecursive(text, chunkSize, separatorIndex + 1);
        }
        return result;
    }

    private List<TextChunk> mergePieces(
            List<Piece> pieces,
            int chunkSize,
            int overlap,
            int textLength
    ) {
        List<TextChunk> chunks = new ArrayList<>();
        StringBuilder buffer = new StringBuilder();
        int index = 0;
        int chunkStart = -1;
        int chunkEnd = -1;

        for (Piece piece : pieces) {
            if (buffer.length() > 0
                    && buffer.length() + piece.content().length() + 1
                    > chunkSize) {
                // 输出当前 Chunk（带真实近似偏移）。
                chunks.add(buildChunk(
                        index++,
                        buffer.toString(),
                        chunkStart,
                        chunkEnd
                ));

                // 重叠：取上一 Chunk 尾部 overlap 字符作为下一切片起点。
                String current = buffer.toString();
                buffer.setLength(0);
                if (current.length() > overlap && overlap > 0) {
                    String overlapText = current.substring(
                            current.length() - overlap
                    );
                    buffer.append(overlapText);
                    chunkStart = Math.max(0, chunkEnd - overlapText.length());
                } else {
                    chunkStart = piece.start();
                }
            } else if (buffer.length() == 0) {
                chunkStart = piece.start();
            }

            if (!buffer.isEmpty()) {
                buffer.append("\n");
            }
            buffer.append(piece.content());
            chunkEnd = piece.end();
        }

        if (!buffer.isEmpty()) {
            chunks.add(buildChunk(
                    index,
                    buffer.toString(),
                    chunkStart,
                    textLength
            ));
        }
        return chunks;
    }

    private TextChunk buildChunk(
            int index,
            String content,
            int start,
            int end
    ) {
        return TextChunk.builder()
                .chunkIndex(index)
                .content(content.trim())
                .startOffset(start)
                .endOffset(end)
                .build();
    }

    @Override
    public String type() {
        return "recursive";
    }
}
