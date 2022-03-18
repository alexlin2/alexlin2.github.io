import cv2
import numpy as np 
import os
class MonocularVO():
    
    def __init__(self, focal, pp, detector, lk_params, pose_file_path, start_id):
        self.focal = focal
        self.pp = pp
        self.detector = detector
        self.lk_params = lk_params
        self.features_img = None
        self.lk_img = None
        self.frame_id = start_id
        self.start_id = start_id
        self.min_features = 0
        self.R = np.zeros(shape=(3, 3), dtype=np.float32)
        self.t = np.zeros(shape=(3, 1), dtype=np.float32)
        with open(pose_file_path) as f:
            self.pose = f.readlines()

        self.get_initial_pose()
        print(self.t)

    def get_initial_pose(self):
        start_pose = self.pose[self.start_id].strip().split()
        x = float(start_pose[3])
        y = float(start_pose[7])
        z = float(start_pose[11])
        self.t[0] = -x
        self.t[1] = -y
        self.t[2] = -z
        self.R[0, :] = start_pose[:3]
        self.R[1, :] = start_pose[4:7]
        self.R[2, :] = start_pose[8:11]

    def detect_features(self, frame):

        kp = self.detector.detect(frame)
        cv2.drawKeypoints(self.features_img, kp, None, color=255)
        return np.array([x.pt for x in kp], dtype=np.float32).reshape(-1, 1, 2)

    def lk_optical_flow(self, p0, old_frame, current_frame):

        self.p1, st, _ = cv2.calcOpticalFlowPyrLK(old_frame, current_frame, self.p0, None, **self.lk_params)

        self.good_old = self.p0[st == 1].reshape(-1, 1, 2)
        self.good_new = self.p1[st == 1].reshape(-1, 1, 2)

        mask = np.zeros_like(old_frame)

        for i, (new, old) in enumerate(zip(self.good_new, self.good_old)):
            a, b = new.ravel()
            c, d = old.ravel()
            mask = cv2.line(mask, (int(a), int(b)), (int(c), int(d)), 255, 2)
            lk_img = cv2.circle(old_frame, (int(a), int(b)), 5, 255, -1)
        self.lk_img = cv2.add(lk_img, mask)
        
    def get_absolute_scale(self):

        pose = self.pose[self.frame_id - 1].strip().split()
        x_prev = float(pose[3])
        y_prev = float(pose[7])
        z_prev = float(pose[11])
        pose = self.pose[self.frame_id].strip().split()
        x = float(pose[3])
        y = float(pose[7])
        z = float(pose[11])

        true_vect = np.array([[x], [y], [z]])
        prev_vect = np.array([[x_prev], [y_prev], [z_prev]])

        self.true_coord = true_vect
        
        return np.linalg.norm(true_vect - prev_vect)

    def process_frame(self, old_frame, current_frame):

        self.features_img = current_frame.copy()
        self.lk_img = current_frame.copy()
        
        if self.min_features < 2000:
            self.p0 = self.detect_features(old_frame)

        
        self.lk_optical_flow(self.p0, old_frame, current_frame)

        E, _ = cv2.findEssentialMat(self.good_new, self.good_old, self.focal, self.pp, cv2.RANSAC, 0.999, 1.0, None)

        absolute_scale = self.get_absolute_scale()

  
        _, R, t, _ = cv2.recoverPose(E, self.good_old, self.good_new, focal=self.focal, pp=self.pp)
        
        if (absolute_scale > 0.1 and absolute_scale < 10):
            print(absolute_scale)
            self.t = self.t + absolute_scale * self.R.dot(t)
            self.R = R.dot(self.R)

        self.p0 = self.good_new.reshape(-1, 1, 2)

    def get_predicted_coords(self):
        diag = np.array([[-1, 0, 0],
                        [0, -1, 0],
                        [0, 0, -1]])
        adj_coord = np.matmul(diag, self.t)

        return adj_coord.flatten()

    def get_true_coords(self):
        return self.true_coord.flatten()

if __name__ == '__main__':

    dataset_img_path = '/home/alexlin/Developer/Monocular_VO/dataset/images/00/image_0/'
    dataset_pose_path = '/home/alexlin/Developer/Monocular_VO/dataset/poses/00.txt'
    
    focal = 718.8560
    pp = (607.1928, 185.2157)

    lk_params=dict(winSize  = (21,21), criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))

    fast_detector=cv2.FastFeatureDetector_create(threshold=25, nonmaxSuppression=True)

    vo = MonocularVO(focal, pp, fast_detector, lk_params, dataset_pose_path, 0)

    traj = np.zeros(shape=(600, 800, 3))

    while(vo.frame_id < len(os.listdir(dataset_img_path))):
        old_frame = cv2.imread(dataset_img_path + str(vo.frame_id).zfill(6)+'.png', 0)
        new_frame = cv2.imread(dataset_img_path + str(vo.frame_id+1).zfill(6)+'.png', 0)

        if(old_frame is not None and new_frame is not None):
            cv2.imshow('frame', new_frame)
            vo.process_frame(old_frame, new_frame)

            cv2.imshow('lk_frame', vo.lk_img)
            cv2.imshow('kp_frame', vo.features_img)

            coord = vo.get_predicted_coords()
            true_coord = vo.get_true_coords()
            draw_x, draw_y, draw_z = [int(round(x)) for x in coord]
            true_x, true_y, true_z = [int(round(x)) for x in true_coord]
            traj = cv2.circle(traj, (true_x + 400, true_z + 300), 1, list((0, 0, 255)), 4)
            traj = cv2.circle(traj, (draw_x + 400, draw_z + 300), 1, list((0, 255, 0)), 4)
            
            cv2.imshow('trajectory', traj)

            k = cv2.waitKey(30) & 0xff
            if k == 27:
                break

        vo.frame_id += 1

    cv2.destroyAllWindows()