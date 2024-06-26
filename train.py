coding='utf-8'
import os
from net import Mnet
import torch
import random
import numpy as np
import torch.optim as optim
from torch.utils.data import DataLoader
from lib.dataset import Data
from lib.data_prefetcher import DataPrefetcher
from torch.nn import functional as F
from smooth_loss import get_saliency_smoothness
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

def my_loss1(score,score1,score2,score_g,label):
    sal_loss2 = F.binary_cross_entropy_with_logits(score1, label, reduction='mean')
    sal_loss3 = F.binary_cross_entropy_with_logits(score2, label, reduction='mean')
    sal_loss1 = F.binary_cross_entropy_with_logits(score, label, reduction='mean')
    sml = get_saliency_smoothness(torch.sigmoid(score),label)
    label_g = F.interpolate(label, score_g.shape[2:], mode='bilinear', align_corners=True)
    sal_loss_g = F.binary_cross_entropy_with_logits(score_g, label_g, reduction='mean')
    return sal_loss1 + sal_loss2 + sal_loss3 + 0.5*sml + sal_loss_g

if __name__ == '__main__':
    random.seed(118)
    np.random.seed(118)
    torch.manual_seed(118)
    torch.cuda.manual_seed(118)
    torch.cuda.manual_seed_all(118)
    
    # dataset
    img_root = '../vt5000/Train/'
    save_path = './model'
    # model_path = './model/epoch_20.pth'
    if not os.path.exists(save_path): os.mkdir(save_path)
    lr = 0.001
    batch_size = 2
    epoch = 63
    lr_dec = [21, 47]
    num_params = 0
    data = Data(img_root)
    loader = DataLoader(data, batch_size=batch_size, shuffle=True, num_workers=8)
    net = Mnet().cuda()
    net.load_pretrained_model()
    # print('loading model from %s...' % model_path)
    # net.load_state_dict(torch.load(model_path))
    optimizer = optim.SGD(filter(lambda p: p.requires_grad, net.parameters()), lr=lr, weight_decay=0.0005, momentum=0.9)
    for p in net.parameters():
        num_params += p.numel()
    print("The number of parameters: {}".format(num_params))
    iter_num = len(loader)
    net.train()

    for epochi in range(1, epoch + 1):
        if epochi in lr_dec:
            lr = lr/10
            optimizer = optim.SGD(filter(lambda p: p.requires_grad, net.parameters()), lr=lr, weight_decay=0.0005, momentum=0.9)
            print(lr)
        prefetcher = DataPrefetcher(loader)
        rgb, t, label = prefetcher.next()
        r_sal_loss = 0
        epoch_ave_loss = 0
        net.zero_grad()
        i = 0
        while rgb is not None:
            i+=1
            score, score1, score2, g = net(rgb, t)
            sal_loss = my_loss1(score, score1, score2, g, label)
            r_sal_loss += sal_loss.data
            sal_loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            if i % 100 == 0:
                print('epoch: [%2d/%2d], iter: [%5d/%5d]  ||  loss : %5.4f, lr: %7.6f' % (
                    epochi, epoch, i, iter_num, r_sal_loss / 100, lr,))
                epoch_ave_loss += (r_sal_loss/100)
                r_sal_loss = 0
            rgb, t, label = prefetcher.next()
        print('epoch-%2d_ave_loss: %7.6f' % (epochi, (epoch_ave_loss / (25/batch_size))))
        if (epochi <= 45) and (epochi % 10 == 0):
            torch.save(net.state_dict(), '%s/epoch_%d.pth' % (save_path, epochi))
        elif (epochi > 45) and (epochi % 1 == 0):
            torch.save(net.state_dict(), '%s/epoch_%d.pth' % (save_path, epochi))

    torch.save(net.state_dict(), '%s/final.pth' % (save_path))