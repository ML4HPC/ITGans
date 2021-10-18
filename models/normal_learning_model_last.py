import torch
import torch.nn as nn
import pdb
import torch.nn.functional as F
from torch.nn.parameter import Parameter
from models import FinalRowWise_layer
from models import modified_GRU
import numpy as np
from sklearn.preprocessing import normalize
import matplotlib.pyplot as plt
from torch.autograd import Variable
from scipy.stats import sem

## granger full rank
class Model(nn.Module):
    def __init__(self, args, data, major_graph):
        super(Model, self).__init__()
        self.use_cuda = args.cuda
        self.m = data.m
        self.w = args.normal_win
        self.num_class = args.num_class
        self.major_graph = major_graph


        self.y_dim = args.y_dim
        self.pre_win = args.normal_prewin
        self.batch_size = args.batch_size
        
        self.reduce_dim = args.reduce_dim;
        self.RUC_layers = args.RUC_layers
        self.hidden_dim = args.hidden_dim

        
        self.dropout = nn.Dropout(args.dropout);
        self.dropout2 = nn.Dropout(0.5);
        
        self.H_init = nn.Parameter(torch.zeros(self.RUC_layers, self.m, self.hidden_dim), requires_grad=True)    

        self.sparse_label = []
        self.orthgonal_label = []
        


        ## GRU
        self.linears = [(modified_GRU.GRUCell(1, self.hidden_dim, args.dropout))]; #0
        self.sparse_label.append(0); self.orthgonal_label.append(1);
        if self.RUC_layers>1:
            for p_i in np.arange(1,self.RUC_layers):
                self.linears.append( (modified_GRU.GRUCell(self.hidden_dim, self.hidden_dim, args.dropout))); #w->hid
                self.sparse_label.append(0); self.orthgonal_label.append(1); 

        ## causal learning ## 
        for idx_class in range(self.num_class):


        ## rolling ##1          
            self.linears.append(nn.utils.weight_norm(nn.Linear(self.RUC_layers*self.hidden_dim, self.reduce_dim, bias = True))); #w->hid
            self.sparse_label.append(0); self.orthgonal_label.append(1);
        
        ## regression ##1     
            self.linears.append(FinalRowWise_layer.FR_Model(args, self.reduce_dim)); #k->k  
            self.sparse_label.append(1); self.orthgonal_label.append(0);  
              
        self.linears = nn.ModuleList(self.linears);


    def forward(self, inputs):
          
        x_input = inputs[0] #nxpxm 
        batch_size = x_input.shape[0]
        x = self.dropout(x_input) 
        
        x = x.transpose(2,1)
        
        h0 = self.H_init.unsqueeze(3).repeat(1, 1, 1, batch_size).transpose(3,1).transpose(3,2); 
        hn = h0[0,:,:,:]
        
        final_y_class = [[] for idx_class in range(self.num_class)]
        for window_i in range(self.w):
                       
            x_org = x[:, :, window_i][:, :, None]

            hn_all = []
            hn = self.linears[0](x_org,hn) 
            hn_all.append(hn)
            if self.RUC_layers>1:
                for p_i in np.arange(1,self.RUC_layers):
                    hn = self.linears[p_i](hn, h0[p_i,:,:,:])
                    hn_all.append(hn)
                       
            x_p = torch.cat(hn_all, dim = 2).transpose(2,1) ## nxhxm

            x_p_idx = F.linear(x_p, self.major_graph.transpose(0,1), bias = None)
            x_p_idx = torch.relu(x_p_idx/1.);
                    
            x_p_idx = self.dropout(x_p_idx).transpose(2,1);  ## nxmxh (causal) ]           
            ## rolling inter class 1
            x_p_idx = self.linears[self.RUC_layers + 0](x_p_idx); ## nxmxr (causal)   
            x_p_idx = torch.sigmoid(x_p_idx/1.);
            x_p_idx = self.dropout(x_p_idx);
            #regession class 1      
            final_y_tmp_1 = self.linears[self.RUC_layers + 1](x_p_idx).squeeze()
            final_y_class[0].append(final_y_tmp_1)
            
        
        final = torch.stack(final_y_class[0]).transpose(1,0) 
       
        return final      
 
         