package com.example.rag.ingestion.chunk;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * ParagraphTextChunker
 * 段落切分器。
 * @author gel
 * @date 2026/7/4
 * @description 
 */
@Component
@RequiredArgsConstructor
public class ParagraphTextChunker implements TextChunker{
    private final FixedSizeTextChunker fixedSizeTextChunker;
    private static final Pattern PARA_SEP = Pattern.compile("\\R\\s*\\R");
    // 段落片段，携带在原文本中的起止偏移
    private record Para(String content, int start, int end) {}



    @Override
    public List<TextChunk> chunk(String text, int chunkSize, int overlap) {
        List<TextChunk> chunks = new ArrayList<>();
        if (text == null || text.isBlank()) {
            return chunks;
        }
        // 用 Matcher 逐一提取段落，精确记录每个段落在原文中的 start/end
        List<Para> paragraphs = extractParagraphs(text);

        StringBuilder buffer = new StringBuilder();
        int index = 0;
        int chunkStart = 0;
        int lastParaEnd = 0;   // buffer 尾部对应的原文结束位置

        for (Para para : paragraphs) {
            if (para.content.length() > chunkSize) {
                // 先输出已经累积的段落内容。
                if (!buffer.isEmpty()) {
                    chunks.add(buildChunk(
                            index++,
                            buffer.toString(),
                            chunkStart,
                            lastParaEnd
                    ));
                    buffer.setLength(0);
                }
                // 超长段落降级为固定长度切分。
                List<TextChunk> fixedChunks = fixedSizeTextChunker.chunk(
                        text.substring(para.start, para.end),
                        chunkSize,
                        overlap
                );
                for (TextChunk fixedChunk : fixedChunks) {
                    fixedChunk.setChunkIndex(index++);
                    // 偏移相对 subString，需平移到原文（+ para.start）。
                    fixedChunk.setStartOffset(
                            fixedChunk.getStartOffset() + para.start
                    );
                    fixedChunk.setEndOffset(
                            fixedChunk.getEndOffset() + para.start
                    );
                    chunks.add(fixedChunk);
                }
                // 游标跳过当前超长段落。
                chunkStart = para.end;
                lastParaEnd = para.end;
                continue;
            }

            // 当前 buffer + 新段落超过 chunkSize → 输出一个 Chunk。
            int sepLen = buffer.isEmpty() ? 0 : 2; // 合并时用 \n\n 连接
            if (buffer.length() > 0
                    && buffer.length() + sepLen + para.content.length()
                    > chunkSize) {
                // 当前累计内容达到目标长度，输出一个 Chunk。
                chunks.add(buildChunk(
                        index++,
                        buffer.toString(),
                        chunkStart,
                        lastParaEnd
                ));

                // overlap 回溯：取上一 Chunk 尾部 overlap 字符，偏移近似。
                String remaining = buffer.toString();
                buffer.setLength(0);
                int overlapStart = Math.max(0, remaining.length() - overlap);
                String overlapText = remaining.substring(overlapStart);
                if (!overlapText.isBlank()) {
                    buffer.append(overlapText);
                    chunkStart = Math.max(
                            0,
                            lastParaEnd - overlapText.length()
                    );
                } else {
                    chunkStart = para.start;
                }
            }

            // 新 Chunk 起点：buffer 为空时从当前段落开始。
            if (buffer.isEmpty()) {
                chunkStart = para.start;
            }
            if (!buffer.isEmpty()) {
                buffer.append("\n\n");
            }
            buffer.append(para.content);
            lastParaEnd = para.end;
        }

        // 处理循环结束后 buffer 中剩余的内容。
        if (!buffer.isEmpty()) {
            chunks.add(buildChunk(index, buffer.toString(), chunkStart, text.length()));
        }
        return chunks;
    }
    private TextChunk buildChunk(int index, String content, int start, int end) {
        return TextChunk.builder()
                .chunkIndex(index)
                .content(content.trim())
                .startOffset(start)
                .endOffset(end)
                .build();
    }
    /** 用 Matcher 提取段落，保留下每个段落在原文中的精确起止位置 */
    private List<Para> extractParagraphs(String text) {
        List<Para> result = new ArrayList<>();
        Matcher matcher = PARA_SEP.matcher(text);
        int pos = 0;
        while (matcher.find()) {
            String content = text.substring(pos, matcher.start()).trim();
            if (!content.isBlank()) {
                result.add(new Para(content, pos, matcher.start()));
            }
            pos = matcher.end(); // matcher.end() = 分隔符的实际结束位置
        }
        // 最后一个段落（后面没有分隔符）
        String last = text.substring(pos).trim();
        if (!last.isBlank()) {
            result.add(new Para(last, pos, text.length()));
        }
        return result;
    }



    @Override
    public String type() {
        return "paragraph";
    }
}
