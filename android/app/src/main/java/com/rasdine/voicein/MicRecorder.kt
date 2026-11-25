package com.rasdine.voicein

import android.content.Context
import android.media.MediaRecorder
import android.os.Build
import java.io.File
import java.io.IOException

/** AAC in an MPEG-4 file. The server maps `audio/mp4` to `recording.mp4`. */
internal class MicRecorder(private val context: Context) {
    private var recorder: MediaRecorder? = null
    private var file: File? = null

    val isRecording: Boolean
        get() = recorder != null

    fun start() {
        discard()
        val out = File(context.cacheDir, "recording.m4a")
        if (out.exists() && !out.delete()) {
            throw IOException("Could not replace the previous recording.")
        }
        val rec = create()
        try {
            rec.setAudioSource(MediaRecorder.AudioSource.MIC)
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            rec.setAudioChannels(1)
            rec.setAudioSamplingRate(44_100)
            rec.setAudioEncodingBitRate(64_000)
            rec.setOutputFile(out.absolutePath)
            rec.prepare()
            rec.start()
        } catch (e: RuntimeException) {
            rec.release()
            out.delete()
            throw e
        } catch (e: IOException) {
            rec.release()
            out.delete()
            throw e
        }
        recorder = rec
        file = out
    }

    fun stop(): ByteArray {
        val rec = recorder ?: throw IllegalStateException("Not recording")
        val out = file
        recorder = null
        file = null
        try {
            rec.stop()
        } catch (e: RuntimeException) {
            rec.release()
            out?.delete()
            throw IOException("Recording was too short.", e)
        }
        rec.release()
        try {
            return out?.takeIf { it.isFile }?.readBytes() ?: ByteArray(0)
        } finally {
            out?.delete()
        }
    }

    fun discard() {
        val rec = recorder ?: return
        recorder = null
        try {
            rec.stop()
        } catch (_: RuntimeException) {
            // stop() throws when the capture never produced a frame.
        }
        rec.release()
        file?.delete()
        file = null
    }

    private fun create(): MediaRecorder {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(context)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
    }
}
