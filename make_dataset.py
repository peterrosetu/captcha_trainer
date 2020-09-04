#!/usr/bin/env python3
# -*- coding:utf-8 -*-
# Author: kerlomz <kerlomz@gmail.com>
import sys
import random
from tqdm import tqdm
import tensorflow as tf
from config import *
from constants import RunMode

_RANDOM_SEED = 0


class DataSets:

    """此类用于打包数据集为TFRecords格式"""
    def __init__(self, model: ModelConfig):
        self.ignore_list = ["Thumbs.db", ".DS_Store"]
        self.model: ModelConfig = model
        if not os.path.exists(self.model.dataset_root_path):
            os.makedirs(self.model.dataset_root_path)

    @staticmethod
    def read_image(path):
        """
        读取图片
        :param path: 图片路径
        :return:
        """
        with open(path, "rb") as f:
            return f.read()

    def dataset_exists(self):
        """数据集是否存在判断函数"""
        for file in (self.model.trains_path[DatasetType.TFRecords] + self.model.validation_path[DatasetType.TFRecords]):
            if not os.path.exists(file):
                return False
        return True

    @staticmethod
    def bytes_feature(values):
        return tf.train.Feature(bytes_list=tf.train.BytesList(value=[values]))

    def input_to_tfrecords(self, input_data, label):
        return tf.train.Example(features=tf.train.Features(feature={
            'input': self.bytes_feature(input_data),
            'label': self.bytes_feature(label),
        }))

    def convert_dataset_from_filename(self, output_filename, file_list, mode: RunMode, is_add=False):
        if is_add:
            output_filename = self.model.dataset_increasing_name(mode)
            if not output_filename:
                raise FileNotFoundError('Basic data set missing, please check.')
            output_filename = os.path.join(self.model.dataset_root_path, output_filename)
        with tf.io.TFRecordWriter(output_filename) as writer:
            pbar = tqdm(file_list)
            for i, file_name in enumerate(pbar):
                try:
                    if file_name.split("/")[-1] in self.ignore_list:
                        continue
                    image_data = self.read_image(file_name)
                    try:
                        labels = re.search(self.model.extract_regex, file_name.split(PATH_SPLIT)[-1])
                    except re.error as e:
                        print('error:', e)
                        return
                    if labels:
                        labels = labels.group()
                    else:
                        tf.logging.warning('invalid filename {}, ignored.'.format(file_name))
                        continue
                        # raise NameError('invalid filename {}'.format(file_name))
                    labels = labels.encode('utf-8')

                    example = self.input_to_tfrecords(image_data, labels)
                    writer.write(example.SerializeToString())
                    pbar.set_description('[Processing dataset %s] [filename: %s]' % (mode, file_name))

                except IOError as e:
                    print('could not read:', file_list[1])
                    print('error:', e)
                    print('skip it \n')

    def convert_dataset_from_txt(self, output_filename, file_path, label_lines, mode: RunMode, is_add=False):
        if is_add:
            output_filename = self.model.dataset_increasing_name(mode)
            if not output_filename:
                raise FileNotFoundError('Basic data set missing, please check.')
            output_filename = os.path.join(self.model.dataset_root_path, output_filename)
        file_list, label_list = [], []
        for line in label_lines:
            filename, label = line.split(" ", 1)
            label = label.replace("\n", "")
            label_list.append(label.encode('utf-8'))
            path = os.path.join(file_path, filename)
            file_list.append(path)

        if os.path.exists(output_filename):
            print('已存在, 跳过')
            return

        with tf.io.TFRecordWriter(output_filename) as writer:
            pbar = tqdm(file_list)
            for i, file_name in enumerate(pbar):
                try:
                    image_data = self.read_image(file_name)
                    labels = label_list[i]
                    example = self.input_to_tfrecords(image_data, labels)
                    writer.write(example.SerializeToString())
                    pbar.set_description('[Processing dataset %s] [filename: %s]' % (mode, file_name))
                except IOError as e:
                    print('could not read:', file_list[1])
                    print('error:', e)
                    print('skip it \n')

    @staticmethod
    def merge_source(source):
        if isinstance(source, list):
            origin_dataset = []
            for trains_path in source:
                origin_dataset += [
                    os.path.join(trains_path, trains).replace("\\", "/") for trains in os.listdir(trains_path)
                ]
        elif isinstance(source, str):
            origin_dataset = [os.path.join(source, trains) for trains in os.listdir(source)]
        else:
            return
        random.seed(0)
        random.shuffle(origin_dataset)
        return origin_dataset

    def make_dataset(self, trains_path=None, validation_path=None, is_add=False, callback=None, msg=None):
        if self.dataset_exists() and not is_add:
            state = "EXISTS"
            if callback:
                callback()
            if msg:
                msg(state)
            return

        if not self.model.dataset_path_root:
            state = "CONF_ERROR"
            if callback:
                callback()
            if msg:
                msg(state)
            return

        trains_path = trains_path if is_add else self.model.trains_path[DatasetType.Directory]
        validation_path = validation_path if is_add else self.model.validation_path[DatasetType.Directory]

        trains_path = [trains_path] if isinstance(trains_path, str) else trains_path
        validation_path = [validation_path] if isinstance(validation_path, str) else validation_path

        if validation_path and not is_add:
            if self.model.label_from == LabelFrom.FileName:
                trains_dataset = self.merge_source(trains_path)
                validation_dataset = self.merge_source(validation_path)
                self.convert_dataset_from_filename(
                    self.model.validation_path[DatasetType.TFRecords][-1 if is_add else 0],
                    validation_dataset,
                    mode=RunMode.Validation,
                    is_add=is_add,
                )
                self.convert_dataset_from_filename(
                    self.model.trains_path[DatasetType.TFRecords][-1 if is_add else 0],
                    trains_dataset,
                    mode=RunMode.Trains,
                    is_add=is_add,
                )
            elif self.model.label_from == LabelFrom.TXT:

                train_label_file = os.path.join(os.path.dirname(trains_path[0]), "train.txt")
                val_label_file = os.path.join(os.path.dirname(validation_path[0]), "val.txt")

                if not os.path.exists(train_label_file) or not os.path.exists(val_label_file):
                    msg("Train or validation label file not found!")
                    if callback:
                        callback()
                    return

                with open(train_label_file, "r", encoding="utf8") as f_train:
                    train_label_line = f_train.readlines()

                with open(val_label_file, "r", encoding="utf8") as f_val:
                    val_label_line = f_val.readlines()

                self.convert_dataset_from_txt(
                    self.model.validation_path[DatasetType.TFRecords][-1 if is_add else 0],
                    label_lines=val_label_line,
                    file_path=validation_path[0],
                    mode=RunMode.Validation,
                    is_add=is_add,
                )
                self.convert_dataset_from_txt(
                    self.model.trains_path[DatasetType.TFRecords][-1 if is_add else 0],
                    label_lines=train_label_line,
                    file_path=trains_path[0],
                    mode=RunMode.Trains,
                    is_add=is_add,
                )

        else:
            if self.model.label_from == LabelFrom.FileName:
                origin_dataset = self.merge_source(trains_path)
                trains_dataset = origin_dataset[self.model.validation_set_num:]
                if self.model.validation_set_num > 0:
                    validation_dataset = origin_dataset[:self.model.validation_set_num]
                    self.convert_dataset_from_filename(
                        self.model.validation_path[DatasetType.TFRecords][-1 if is_add else 0],
                        validation_dataset,
                        mode=RunMode.Validation,
                        is_add=is_add
                    )
                elif self.model.validation_set_num < 0:
                    self.convert_dataset_from_filename(
                        self.model.validation_path[DatasetType.TFRecords][-1 if is_add else 0],
                        trains_dataset,
                        mode=RunMode.Validation,
                        is_add=is_add
                    )
                self.convert_dataset_from_filename(
                    self.model.trains_path[DatasetType.TFRecords][-1 if is_add else 0],
                    trains_dataset,
                    mode=RunMode.Trains,
                    is_add=is_add
                )
            elif self.model.label_from == LabelFrom.TXT:

                train_label_file = os.path.join(os.path.dirname(trains_path[0]), "train.txt")

                if not os.path.exists(train_label_file):
                    msg("Train label file not found!")
                    if callback:
                        callback()
                    return

                with open(train_label_file, "r", encoding="utf8") as f:
                    sample_label_line = f.readlines()

                random.shuffle(sample_label_line)

                train_label_line = sample_label_line[self.model.validation_set_num:]
                val_label_line = sample_label_line[:self.model.validation_set_num]

                self.convert_dataset_from_txt(
                    self.model.validation_path[DatasetType.TFRecords][-1 if is_add else 0],
                    label_lines=val_label_line,
                    file_path=trains_path[0],
                    mode=RunMode.Validation,
                    is_add=is_add,
                )
                self.convert_dataset_from_txt(
                    self.model.trains_path[DatasetType.TFRecords][-1 if is_add else 0],
                    label_lines=train_label_line,
                    file_path=trains_path[0],
                    mode=RunMode.Trains,
                    is_add=is_add,
                )

        state = "DONE"
        if callback:
            callback()
        if msg:
            msg(state)
        return


if __name__ == '__main__':
    model_conf = ModelConfig(sys.argv[-1])
    _dataset = DataSets(model_conf)
    _dataset.make_dataset()
