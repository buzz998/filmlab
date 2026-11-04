# 人脸模型

`face_detection_yunet_2023mar.onnx` 是 OpenCV 官方的 YuNet 人脸检测模型，来自 [opencv/opencv_zoo](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)，MIT 许可。

`develop.py` 用它找人脸，给脸做暗房"遮挡"：同一张底片按两种相纸曝光各放一次，脸那块用亮的，边缘慢慢过渡，天空、白衣服这些本来就亮的地方不跟着提。不想要就加 `--no-dodge`。
