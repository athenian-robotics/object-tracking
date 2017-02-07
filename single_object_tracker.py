#!/usr/bin/env python2

import logging
import time
import traceback
from logging import info

import cv2
import grpc_support
import image_server
import imutils
import opencv_defaults as defs
from common_constants import LOGGING_ARGS
from common_utils import is_raspi
from generic_object_tracker import GenericObjectTracker
from opencv_utils import BLUE, GREEN, RED
from opencv_utils import get_list_arg, get_moment


class SingleObjectTracker(GenericObjectTracker):
    def __init__(self,
                 bgr_color,
                 width,
                 percent,
                 minimum,
                 hsv_range,
                 grpc_port=grpc_support.grpc_port_default,
                 display=False,
                 flip_x=False,
                 flip_y=False,
                 usb_camera=False,
                 leds=False,
                 camera_name="",
                 http_host=image_server.http_host_default,
                 http_delay_secs=image_server.http_delay_secs_default,
                 http_path=image_server.http_path_default):
        super(SingleObjectTracker, self).__init__(bgr_color,
                                                  width,
                                                  percent,
                                                  minimum,
                                                  hsv_range,
                                                  grpc_port=grpc_port,
                                                  display=display,
                                                  flip_x=flip_x,
                                                  flip_y=flip_y,
                                                  usb_camera=usb_camera,
                                                  leds=leds,
                                                  camera_name=camera_name,
                                                  http_host=http_host,
                                                  http_delay_secs=http_delay_secs,
                                                  http_path=http_path)

    # Do not run this in a background thread. cv2.waitKey has to run in main thread
    def start(self):
        super(SingleObjectTracker, self).start()

        while self.cam.is_open() and not self.stopped:
            try:
                image = self.cam.read()
                image = imutils.resize(image, width=self.width)

                if self.flip_x:
                    image = cv2.flip(image, 0)

                if self.flip_y:
                    image = cv2.flip(image, 1)

                middle_pct = (self.percent / 100.0) / 2
                img_height, img_width = image.shape[:2]

                # Called once we know the dimensions of the images
                self.http_server.serve_images(img_width, img_height)

                mid_x, mid_y = img_width / 2, img_height / 2
                img_x, img_y = -1, -1

                # The middle margin calculation is based on % of width for horizontal and vertical boundry
                middle_inc = int(mid_x * middle_pct)

                text = "#{0} ({1}, {2})".format(self.cnt, img_width, img_height)
                text += " {0}%".format(self.percent)

                # Find the largest contour
                contours = self.contour_finder.get_max_contours(image, self.minimum, count=1)

                if contours is not None and len(contours) == 1:
                    contour, area, img_x, img_y = get_moment(contours[0])

                    if self.markup_image:
                        x, y, w, h = cv2.boundingRect(contour)
                        cv2.rectangle(image, (x, y), (x + w, y + h), BLUE, 2)
                        cv2.drawContours(image, [contour], -1, GREEN, 2)
                        cv2.circle(image, (img_x, img_y), 4, RED, -1)
                        text += " ({0}, {1})".format(img_x, img_y)
                        text += " {0}".format(area)

                x_in_middle = mid_x - middle_inc <= img_x <= mid_x + middle_inc
                y_in_middle = mid_y - middle_inc <= img_y <= mid_y + middle_inc

                x_color = GREEN if x_in_middle else RED if img_x == -1 else BLUE
                y_color = GREEN if y_in_middle else RED if img_y == -1 else BLUE

                # Set Blinkt leds
                self.set_left_leds(x_color)
                self.set_right_leds(y_color)

                # Write location if it is different from previous value written
                if img_x != self._prev_x or img_y != self._prev_y:
                    self.location_server.write_location(img_x, img_y, img_width, img_height, middle_inc)
                    self._prev_x, self._prev_y = img_x, img_y

                if self.markup_image:
                    # Draw the alignment lines
                    cv2.line(image, (mid_x - middle_inc, 0), (mid_x - middle_inc, img_height), x_color, 1)
                    cv2.line(image, (mid_x + middle_inc, 0), (mid_x + middle_inc, img_height), x_color, 1)
                    cv2.line(image, (0, mid_y - middle_inc), (img_width, mid_y - middle_inc), y_color, 1)
                    cv2.line(image, (0, mid_y + middle_inc), (img_width, mid_y + middle_inc), y_color, 1)

                    cv2.putText(image, text, defs.TEXT_LOC, defs.TEXT_FONT, defs.TEXT_SIZE, RED, 1)

                self.display_image(image)
                self.serve_image(image)

                self.cnt += 1

            except KeyboardInterrupt as e:
                raise e
            except BaseException as e:
                logging.error("Unexpected error in main loop [{0}]".format(e))
                traceback.print_exc()
                time.sleep(1)

        self.clear_leds()
        self.cam.close()


if __name__ == "__main__":
    # Parse CLI args
    args = GenericObjectTracker.cli_args()

    # Setup logging
    logging.basicConfig(**LOGGING_ARGS)

    object_tracker = SingleObjectTracker(get_list_arg(args["bgr"]),
                                         args["width"],
                                         args["percent"],
                                         args["min"],
                                         args["range"],
                                         grpc_port=args["port"],
                                         display=args["display"],
                                         flip_x=args["flipx"],
                                         flip_y=args["flipy"],
                                         usb_camera=args["usb"],
                                         leds=args["leds"] and is_raspi(),
                                         camera_name=args["camera"],
                                         http_host=args["http"],
                                         http_delay_secs=args["delay"],
                                         http_path=args["path"])
    try:
        object_tracker.start()
    except KeyboardInterrupt:
        pass
    finally:
        object_tracker.stop()

    info("Exiting...")
